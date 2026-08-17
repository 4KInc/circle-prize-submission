"""BlockIntel risk-scoring engine.

Multi-signal risk scorer for AI agent payment intents. Each signal
checks a real property of the transaction — no RNG, no hash-modulo
proxies. When confidence is low, the three-state engine triggers
STEP_UP (autonomous evidence purchase).

Signals are deterministic: same input always produces same score.
In production, BlockIntel's full model adds ML-based behavioral
clustering and real-time chain indexing. This scorer demonstrates
the decision interface with signals that inspect actual input data.

The score drives Verigate's three-state decision engine:
  APPROVE  — policy passes, risk below threshold
  STEP_UP  — policy passes, risk uncertain, purchase verification
  DENY     — policy fails or risk above threshold
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from circle.behavioral import BehavioralEngine

MODEL_VERSION = "blockintel-heuristic-v2"
FEATURE_VERSION = "signals-v2"

# Decision thresholds
APPROVE_CEILING = 39       # score 0-39 → APPROVE
STEP_UP_CEILING = 74       # score 40-74 → STEP_UP
DENY_FLOOR = 75            # score 75-100 → DENY
CONFIDENCE_FLOOR = 0.60    # below this → STEP_UP regardless of score

# ── Sanctioned addresses (real OFAC SDN designations) ────────────────
# Screening is delegated to circle.sanctions, which maintains the active
# set: a hand-verified static seed of genuinely OFAC-listed ETH addresses,
# optionally merged with a live sync of OFAC's official SDN export. The
# active list's provenance (source, publish date, content digest) is
# attested inside every receipt via `sanctions_feed`.
#
# `SANCTIONED_ADDRESSES` is re-exported for backward compatibility and
# equals the always-available static seed. Live-synced additions are
# reachable via circle.sanctions.active_addresses(). Screening is EXACT
# match only — no prefix heuristics that would produce false positives.
from circle import sanctions as _sanctions  # noqa: E402 — placed after the doc block above by design

SANCTIONED_ADDRESSES = _sanctions.STATIC_OFAC_ETH

# Known high-risk service name patterns
HIGH_RISK_SERVICES = frozenset({
    "mixer", "tumbler", "tornado", "blender", "washer",
    "anonymous-transfer", "privacy-swap",
})

# ── Payee grammars ───────────────────────────────────────────────────
# A payee is either a wallet (direct USDC transfer) or an x402 service
# endpoint (HTTP resource that settles to a wallet behind it). These are
# screened differently, so they are recognised separately.
EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
# Hostname: dot-separated LDH labels, no leading/trailing hyphen, alpha TLD.
HOSTNAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)

# x402 service providers with established reputation. Membership means the
# endpoint is a recognised counterparty, not that its payments are approved —
# amount, injection, and behavioural signals still apply.
KNOWN_X402_ENDPOINTS = frozenset({
    "blockrun.ai",
    "api.blockrun.ai",
    "verigate.cloud",
})

# ── Prompt injection structural patterns ─────────────────────────────
# These detect *structural* injection, not just keywords. Each pattern
# targets a specific attack technique used against LLM-driven agents.
INJECTION_PATTERNS = [
    # Role/identity hijacking
    (re.compile(r"(?:you are|act as|pretend to be|your (?:new )?role is)", re.I), "role_hijack", 20),
    # Instruction override — tolerate stacked qualifiers ("all previous")
    # and the common override verbs.
    (re.compile(r"(?:ignore|disregard|forget|override|bypass)\s+(?:(?:all|any|previous|prior|the|your)\s+)*(?:instructions?|rules?|policies?|constraints?|guidelines?|directives?)", re.I), "instruction_override", 25),
    # System prompt leakage
    (re.compile(r"(?:system\s*(?:prompt|override|message)|<\|?system\|?>)", re.I), "system_prompt_inject", 25),
    # Urgency manipulation (social engineering) — allow punctuation between
    # the urgency cue and the action verb ("URGENT: transfer", "now, send").
    (re.compile(r"(?:urgent(?:ly)?|immediate(?:ly)?|emergency|asap|right\s*now)[\s:;,.\-]+(?:transfer|send|pay|move|withdraw|wire|release)", re.I), "urgency_manipulation", 15),
    # Authority impersonation
    (re.compile(r"(?:authorized?\s+by|approved?\s+by|(?:ceo|cto|cfo|admin|founder)\s+(?:said|approved|authorized))", re.I), "authority_spoof", 20),
    # Delimiter injection
    (re.compile(r"(?:```|---\n|###\s|={3,})", re.I), "delimiter_inject", 10),
]


@dataclass
class RiskAssessment:
    score: int                          # 0-100
    band: str                           # LOW, MEDIUM, HIGH, CRITICAL
    confidence: float                   # 0.0-1.0
    signals: list[str] = field(default_factory=list)
    signal_details: dict = field(default_factory=dict)
    model_version: str = MODEL_VERSION
    feature_version: str = FEATURE_VERSION
    evaluated_at: str = ""
    sanctions_feed: dict = field(default_factory=dict)  # OFAC list provenance
    contributions: list[dict] = field(default_factory=list)  # per-category score attribution
    rationale: str = ""                 # human-readable "why this decision"

    def __post_init__(self):
        if not self.evaluated_at:
            self.evaluated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @property
    def decision(self) -> str:
        """Determine decision based on thresholds."""
        if self.score <= APPROVE_CEILING and self.confidence >= CONFIDENCE_FLOOR:
            return "APPROVE"
        if self.score >= DENY_FLOOR and self.confidence >= CONFIDENCE_FLOOR:
            return "DENY"
        return "STEP_UP"

    def to_dict(self) -> dict:
        """Return serializable dict. All values are strings/lists/ints
        to avoid float canonicalization errors in receipt signing."""
        return {
            "risk_score": self.score,
            "risk_band": self.band,
            "confidence": str(self.confidence),
            "signals": self.signals,
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "evaluated_at": self.evaluated_at,
            "sanctions_feed": self.sanctions_feed,
            "contributions": self.contributions,
            "rationale": self.rationale,
        }


def _score_band(score: int) -> str:
    if score <= 25:
        return "LOW"
    if score <= 50:
        return "MEDIUM"
    if score <= 75:
        return "HIGH"
    return "CRITICAL"


def _check_sanctions(payee: str) -> tuple[bool, str]:
    """Screen payee against the OFAC SDN address list.

    Exact-match only — the same discipline real compliance systems use.
    Partial/prefix matching is deliberately avoided because it produces
    false positives that would wrongly block legitimate counterparties.
    """
    normalized = payee.lower().strip()
    if normalized in _sanctions.active_addresses():
        return True, f"OFAC SDN exact match: {normalized[:10]}…{normalized[-6:]}"
    return False, ""


def _check_injection(reason: str) -> tuple[int, float, list[str], dict]:
    """Structural prompt injection analysis.

    Returns (score_delta, confidence_delta, signal_names, details).
    """
    score = 0
    signals = []
    details = {}
    matches = 0

    for pattern, signal_name, weight in INJECTION_PATTERNS:
        found = pattern.findall(reason)
        if found:
            matches += 1
            signals.append(signal_name)
            score += weight
            details[signal_name] = found[0] if len(found) == 1 else found[:3]

    # Shannon entropy of the reason text — high entropy can indicate
    # encoded payloads or obfuscated injection attempts
    if len(reason) > 20:
        freq: dict[str, int] = {}
        for c in reason.lower():
            freq[c] = freq.get(c, 0) + 1
        entropy = -sum((f / len(reason)) * math.log2(f / len(reason)) for f in freq.values())
        if entropy > 4.5 and len(reason) > 100:
            signals.append("high_entropy_payload")
            score += 10
            details["entropy"] = round(entropy, 2)

    # Confidence increases with more injection signals (more certain it's an attack)
    confidence_boost = min(matches * 0.05, 0.15) if matches > 0 else 0

    return score, confidence_boost, signals, details


def _check_amount(amount: float, service: str) -> tuple[int, float, list[str], dict]:
    """Amount risk analysis relative to service context."""
    score = 0
    confidence = 0.0
    signals = []
    details = {}

    # Absolute amount thresholds
    if amount > 10.0:
        signals.append("amount_anomaly")
        score += min(int(amount * 3), 40)
        details["amount"] = f"${amount:.2f} exceeds $10 threshold"
    elif amount > 1.0:
        signals.append("elevated_amount")
        score += min(int(amount * 8), 20)
        details["amount"] = f"${amount:.2f} above typical range"
    elif amount > 0.1:
        signals.append("elevated_amount")
        score += 5

    # Service-amount mismatch (data services shouldn't cost $50)
    data_services = {"market-data", "analytics", "price", "research", "data", "feed"}
    if any(s in service.lower() for s in data_services) and amount > 5.0:
        signals.append("service_amount_mismatch")
        score += 15
        confidence -= 0.10
        details["mismatch"] = f"data service at ${amount:.2f} is unusual"

    return score, confidence, signals, details


def _levenshtein(a: str, b: str) -> int:
    """Edit distance, used only for typosquat proximity on short hostnames."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def classify_payee(payee: str) -> str:
    """Classify a payee as an EVM address, an x402 service endpoint, or neither.

    x402 payments name an HTTP resource — the settlement wallet sits behind
    the endpoint and is not visible in the payee field. Both forms are
    legitimate, but they are screenable in different ways, so they must be
    told apart before any format judgement is made.

    Returns one of: "address", "endpoint", "unknown".
    """
    p = payee.lower().strip()

    if EVM_ADDRESS_RE.match(p):
        return "address"

    # Strip a scheme if present; anything other than http(s) is not a payable
    # web resource and falls through to "unknown".
    if "://" in p:
        scheme, _, rest = p.partition("://")
        if scheme not in ("http", "https"):
            return "unknown"
        p = rest

    # Credentials-in-URL is a phishing construction, never a service identity.
    if "@" in p:
        return "unknown"

    host = p.split("/", 1)[0].split("?", 1)[0]
    host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host  # strip :port

    # Bare IP literals are not a service identity we can build reputation on.
    if IPV4_RE.match(host):
        return "unknown"

    return "endpoint" if HOSTNAME_RE.match(host) else "unknown"


def _check_service_endpoint(payee: str) -> tuple[int, float, list[str], dict]:
    """Reputation analysis for an x402 service endpoint.

    Deliberately weaker than address screening, and says so. Sanctions
    screening is an exact match against a wallet list; an endpoint hides its
    settlement wallet, so OFAC coverage is *not* available here. Rather than
    silently returning a clean result, this emits an explicit coverage-gap
    signal and a confidence penalty so the receipt records what was and was
    not checked. Supplying `settlement_address` alongside the endpoint
    restores full screening.
    """
    score = 0
    confidence = 0.0
    signals: list[str] = []
    details: dict = {}

    stripped = payee.split("://", 1)[-1]
    host = stripped.split("/", 1)[0].split("?", 1)[0]
    host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host

    signals.append("service_endpoint")
    details["payee_kind"] = f"x402 service endpoint ({host})"

    # Coverage gap, stated explicitly rather than assumed away.
    signals.append("settlement_address_unavailable")
    confidence -= 0.10
    details["sanctions_coverage"] = (
        "OFAC screening unavailable: endpoint payee hides its settlement wallet. "
        "Pass settlement_address to enable exact-match sanctions screening."
    )

    if payee.startswith("http://"):
        signals.append("insecure_scheme")
        score += 15
        details["scheme"] = "cleartext http:// — endpoint is not authenticated in transit"

    # Punycode is the standard homograph-attack carrier.
    if any(label.startswith("xn--") for label in host.split(".")):
        signals.append("punycode_hostname")
        score += 25
        details["homograph"] = f"punycode label in {host} — possible homograph attack"

    if host in KNOWN_X402_ENDPOINTS:
        details["endpoint_reputation"] = f"{host} is a known x402 service provider"
        return score, confidence, signals, details

    # Typosquat proximity against known providers (b1ockrun.ai vs blockrun.ai).
    for known in KNOWN_X402_ENDPOINTS:
        if _levenshtein(host, known) <= 2:
            signals.append("endpoint_typosquat")
            # Must clear APPROVE_CEILING on its own: a near-miss against a
            # known provider is a targeted attack indicator, and must never
            # approve silently on the strength of an otherwise clean payment.
            score += 45
            confidence += 0.05  # a near-miss is strong evidence, not uncertainty
            details["typosquat"] = f"{host} is {_levenshtein(host, known)} edit(s) from {known}"
            return score, confidence, signals, details

    # Unknown endpoints carry real risk — never score them as clean.
    signals.append("unknown_endpoint")
    score += 10
    confidence -= 0.05
    details["endpoint_reputation"] = f"{host} is not a known x402 service provider"

    return score, confidence, signals, details


def _check_payee(payee: str, known_payees: list[str] | None) -> tuple[int, float, list[str], dict]:
    """Payee reputation analysis."""
    score = 0
    confidence = 0.0
    signals = []
    details = {}

    normalized = payee.lower().strip()
    payee_kind = classify_payee(normalized)

    # Known-good payee
    if known_payees:
        known_lower = [p.lower() for p in known_payees]
        if normalized in known_lower:
            # Known payee — but first transaction still has uncertainty
            signals.append("first_commercial_relationship")
            score += 15
            confidence = -0.30  # forces below CONFIDENCE_FLOOR → STEP_UP
            details["payee"] = "on allowlist but no transaction history"
        else:
            signals.append("unknown_payee")
            score += 20
            confidence = -0.15
            details["payee"] = "not on allowlist"

    # Format validation, dispatched on payee kind. An x402 payee is an HTTP
    # resource, not a wallet — judging it against the EVM address grammar
    # produces a false `malformed_address` on every well-formed service call.
    if payee_kind == "endpoint":
        s, c, sig, det = _check_service_endpoint(normalized)
        score += s
        confidence += c
        signals.extend(sig)
        details.update(det)
        return score, confidence, signals, details

    if payee_kind == "unknown":
        signals.append("malformed_address")
        score += 15
        details["format"] = "neither a valid EVM address nor a valid service endpoint"

    # Null/dead address patterns (real check, not hash-modulo)
    if normalized in ("0x" + "0" * 40, "0x" + "dead" * 10, "0x" + "f" * 40):
        signals.append("null_address")
        score += 30
        details["address_type"] = "null/burn address"

    # High-risk address prefixes (common in attack simulations)
    if normalized.startswith("0xdead") or normalized.startswith("0xbad0") or normalized.startswith("0x0000dead"):
        signals.append("suspicious_address_pattern")
        score += 20
        details["pattern"] = f"prefix {normalized[:8]} associated with test/attack addresses"

    return score, confidence, signals, details


def _check_service(service: str) -> tuple[int, float, list[str], dict]:
    """Service reputation analysis."""
    score = 0
    confidence = 0.0
    signals = []
    details = {}

    service_lower = service.lower()

    # Known high-risk service types
    if any(hrs in service_lower for hrs in HIGH_RISK_SERVICES):
        signals.append("high_risk_service")
        score += 30
        details["service_risk"] = f"'{service}' matches high-risk pattern"

    # Override/admin service names (likely injection artifacts)
    if any(w in service_lower for w in ("override", "admin", "system", "emergency")):
        signals.append("suspicious_service_name")
        score += 15
        details["service_name"] = f"'{service}' contains control keywords"

    return score, confidence, signals, details


def evaluate_risk(
    payee: str,
    amount: str,
    service: str,
    reason: str,
    source_wallet: str,
    chain: str,
    known_payees: list[str] | None = None,
    behavioral: BehavioralEngine | None = None,
) -> RiskAssessment:
    """Evaluate transaction risk using multi-signal analysis.

    Each signal inspects actual properties of the input data:
    - Sanctions screening against the live OFAC SDN list
    - Structural prompt injection detection (not keyword matching)
    - Amount anomaly relative to service context
    - Payee address validation and reputation
    - Service risk classification
    - Behavioral anomaly vs the agent's own history (optional)

    Args:
        behavioral: an optional circle.behavioral.BehavioralEngine. When
            provided, its read-only assessment (amount-deviation, velocity,
            novel-counterparty) is folded into the score. Recording new
            history is the caller's responsibility (engine.record(...)), so
            pre-flight/quick-check scoring never mutates history.
    """
    all_signals = []
    all_details = {}
    contributions: list[dict] = []
    total_score = 0
    confidence = 0.85

    amount_f = float(amount)

    def _add(category: str, score_delta: int, conf_delta: float,
             signals: list[str], detail: object) -> None:
        """Record a category's contribution to the aggregate so the final
        verdict is fully attributable (no black-box scoring)."""
        if score_delta or conf_delta or signals:
            contributions.append({
                "category": category,
                "score_delta": int(score_delta),
                "confidence_delta": round(float(conf_delta), 3),
                "signals": list(signals),
                "detail": detail,
            })

    # 1. Sanctions screening (real OFAC SDN list). A confirmed match is a
    #    hard block: high score + high confidence guarantees a DENY verdict,
    #    never a STEP_UP. There is no "second opinion" on a sanctioned payee.
    is_sanctioned, sanction_detail = _check_sanctions(payee)
    if is_sanctioned:
        all_signals.append("sanctioned_address")
        total_score += 80
        conf_before = confidence
        confidence = 0.99
        all_details["sanctions"] = sanction_detail
        _add("sanctions", 80, confidence - conf_before, ["sanctioned_address"], sanction_detail)

    # 2. Prompt injection (structural analysis). A detected manipulation
    #    attempt in the justification text is disqualifying on its own: we
    #    never auto-APPROVE a payment whose reason is trying to steer the
    #    agent. One signal floors the verdict to STEP_UP; a strong pattern
    #    (override / system-prompt / role hijack) or two+ signals → DENY.
    inj_score, inj_conf, inj_signals, inj_details = _check_injection(reason)
    total_score += inj_score
    confidence += inj_conf
    all_signals.extend(inj_signals)
    all_details.update(inj_details)
    _add("injection", inj_score, inj_conf, inj_signals, inj_details)

    # 3. Amount analysis
    amt_score, amt_conf, amt_signals, amt_details = _check_amount(amount_f, service)
    total_score += amt_score
    confidence += amt_conf
    all_signals.extend(amt_signals)
    all_details.update(amt_details)
    _add("amount", amt_score, amt_conf, amt_signals, amt_details)

    # 4. Payee analysis
    payee_score, payee_conf, payee_signals, payee_details = _check_payee(payee, known_payees)
    total_score += payee_score
    confidence += payee_conf
    all_signals.extend(payee_signals)
    all_details.update(payee_details)
    _add("payee", payee_score, payee_conf, payee_signals, payee_details)

    # 5. Service analysis
    svc_score, svc_conf, svc_signals, svc_details = _check_service(service)
    total_score += svc_score
    confidence += svc_conf
    all_signals.extend(svc_signals)
    all_details.update(svc_details)
    _add("service", svc_score, svc_conf, svc_signals, svc_details)

    # 6. Behavioral anomaly (optional; read-only against agent history)
    if behavioral is not None:
        try:
            bsig = behavioral.assess(source_wallet, payee, amount_f, service)
            total_score += bsig.score
            confidence += bsig.confidence_delta
            all_signals.extend(bsig.signals)
            all_details.update(bsig.details)
            _add("behavioral", bsig.score, bsig.confidence_delta, bsig.signals, bsig.details)
        except Exception:  # noqa: BLE001 — behavioral is advisory, never fatal
            pass

    # Injection escalation (applied after all components accumulate). A
    # detected manipulation attempt in the justification text is
    # disqualifying: we never auto-APPROVE a payment whose reason is trying
    # to steer the agent. One signal floors the verdict to STEP_UP; a strong
    # pattern (override / system-prompt / role hijack) or two+ signals → DENY.
    if inj_signals:
        strong_injection = {"instruction_override", "system_prompt_inject", "role_hijack"}
        pre_esc = total_score
        total_score = max(total_score, APPROVE_CEILING + 1)   # >= 40 → STEP_UP
        if len(inj_signals) >= 2 or (strong_injection & set(inj_signals)):
            total_score = max(total_score, DENY_FLOOR)         # >= 75 → DENY
            confidence = max(confidence, CONFIDENCE_FLOOR)     # ensure DENY, not STEP_UP
        if total_score != pre_esc:
            _add("injection_escalation", total_score - pre_esc, 0.0, [],
                 "manipulation in justification floors the verdict")

    # Clamp
    total_score = max(0, min(total_score, 100))
    confidence = max(0.10, min(confidence, 0.99))

    # No signals → safe baseline
    if not all_signals:
        total_score = max(total_score, 5)
        confidence = 0.95

    confidence = round(confidence, 2)
    assessment = RiskAssessment(
        score=total_score,
        band=_score_band(total_score),
        confidence=confidence,
        signals=all_signals,
        signal_details=all_details,
        sanctions_feed=_sanctions.feed_metadata(),
        contributions=contributions,
    )
    assessment.rationale = _build_rationale(assessment, contributions)
    return assessment


def _build_rationale(assessment: RiskAssessment, contributions: list[dict]) -> str:
    """Explain the verdict in one honest sentence: which threshold rule
    fired and which categories drove the score. No hand-waving — the drivers
    are the exact category deltas that produced this number."""
    decision = assessment.decision
    score = assessment.score
    conf = assessment.confidence
    drivers = sorted(
        (c for c in contributions if c["score_delta"] > 0),
        key=lambda c: c["score_delta"], reverse=True,
    )
    driver_str = ", ".join(f"{c['category']} (+{c['score_delta']})" for c in drivers[:3])
    if not driver_str:
        driver_str = "no risk signals (clean baseline)"

    if decision == "APPROVE":
        rule = f"score {score} ≤ {APPROVE_CEILING} and confidence {conf} ≥ {CONFIDENCE_FLOOR}"
    elif decision == "DENY":
        rule = f"score {score} ≥ {DENY_FLOOR} at confidence {conf} ≥ {CONFIDENCE_FLOOR}"
    else:  # STEP_UP
        if conf < CONFIDENCE_FLOOR:
            rule = f"confidence {conf} < {CONFIDENCE_FLOOR} (uncertain → verify)"
        else:
            rule = f"score {score} in the {APPROVE_CEILING + 1}–{STEP_UP_CEILING} uncertainty band"
    return f"{decision}: {rule}. Primary drivers: {driver_str}."
