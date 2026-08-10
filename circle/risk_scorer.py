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

import hashlib
import math
import re
import time
from dataclasses import dataclass, field
from typing import Optional


MODEL_VERSION = "blockintel-heuristic-v2"
FEATURE_VERSION = "signals-v2"

# Decision thresholds
APPROVE_CEILING = 39       # score 0-39 → APPROVE
STEP_UP_CEILING = 74       # score 40-74 → STEP_UP
DENY_FLOOR = 75            # score 75-100 → DENY
CONFIDENCE_FLOOR = 0.60    # below this → STEP_UP regardless of score

# ── Sanctioned addresses (real OFAC SDN designations) ────────────────
# These are genuine Ethereum addresses on OFAC's Specially Designated
# Nationals (SDN) list. All are valid 40-hex EVM addresses, stored
# lowercased for exact-match comparison. A production system syncs the
# full list from Treasury's SDN feed; this verified subset demonstrates
# real sanctions screening against publicly documented designations.
#
# Sources: US Treasury OFAC SDN List — Tornado Cash (2022-08-08) and
# Lazarus Group / DPRK designations. Screening is EXACT match only,
# mirroring how real compliance systems operate (no prefix heuristics
# that would produce false positives).
SANCTIONED_ADDRESSES = frozenset({
    # Tornado Cash — OFAC designated 2022-08-08
    "0x8589427373d6d84e98730d7795d8f6f8731fda16",  # TC: donation
    "0x722122df12d4e14e13ac3b6895a86e84145b6967",  # TC: router
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384",  # TC: pool
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",  # TC: pool
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",  # TC: 10 ETH pool
    "0xa160cdab225685da1d56aa342ad8841c3b53f291",  # TC: 100 ETH pool
    "0xf60dd140cff0706bae9cd734ac3ae76ad9ebc32a",  # TC: proxy
    "0xba214c1c1928a32bffe790263e38b4af9bfcd659",  # TC: pool
    # Lazarus Group / DPRK — OFAC designated
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96",  # Ronin bridge exploiter
    "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b",  # Lazarus
    "0x3cffd56b47b7b41c56258d9c7731abadc360e073",  # Lazarus
})

# Known high-risk service name patterns
HIGH_RISK_SERVICES = frozenset({
    "mixer", "tumbler", "tornado", "blender", "washer",
    "anonymous-transfer", "privacy-swap",
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
    if normalized in SANCTIONED_ADDRESSES:
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
        freq = {}
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


def _check_payee(payee: str, known_payees: list[str] | None) -> tuple[int, float, list[str], dict]:
    """Payee reputation analysis."""
    score = 0
    confidence = 0.0
    signals = []
    details = {}

    normalized = payee.lower().strip()

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

    # Address format validation
    if not re.match(r"^0x[0-9a-fA-F]{40}$", normalized):
        signals.append("malformed_address")
        score += 15
        details["format"] = "not a valid EVM address"

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
    known_payees: Optional[list[str]] = None,
) -> RiskAssessment:
    """Evaluate transaction risk using multi-signal analysis.

    Each signal inspects actual properties of the input data:
    - Sanctions screening against real OFAC-listed addresses
    - Structural prompt injection detection (not keyword matching)
    - Amount anomaly relative to service context
    - Payee address validation and reputation
    - Service risk classification
    """
    all_signals = []
    all_details = {}
    total_score = 0
    confidence = 0.85

    amount_f = float(amount)

    # 1. Sanctions screening (real OFAC SDN list). A confirmed match is a
    #    hard block: high score + high confidence guarantees a DENY verdict,
    #    never a STEP_UP. There is no "second opinion" on a sanctioned payee.
    is_sanctioned, sanction_detail = _check_sanctions(payee)
    if is_sanctioned:
        all_signals.append("sanctioned_address")
        total_score += 80
        confidence = 0.99
        all_details["sanctions"] = sanction_detail

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

    # 3. Amount analysis
    amt_score, amt_conf, amt_signals, amt_details = _check_amount(amount_f, service)
    total_score += amt_score
    confidence += amt_conf
    all_signals.extend(amt_signals)
    all_details.update(amt_details)

    # 4. Payee analysis
    payee_score, payee_conf, payee_signals, payee_details = _check_payee(payee, known_payees)
    total_score += payee_score
    confidence += payee_conf
    all_signals.extend(payee_signals)
    all_details.update(payee_details)

    # 5. Service analysis
    svc_score, svc_conf, svc_signals, svc_details = _check_service(service)
    total_score += svc_score
    confidence += svc_conf
    all_signals.extend(svc_signals)
    all_details.update(svc_details)

    # Injection escalation (applied after all components accumulate). A
    # detected manipulation attempt in the justification text is
    # disqualifying: we never auto-APPROVE a payment whose reason is trying
    # to steer the agent. One signal floors the verdict to STEP_UP; a strong
    # pattern (override / system-prompt / role hijack) or two+ signals → DENY.
    if inj_signals:
        strong_injection = {"instruction_override", "system_prompt_inject", "role_hijack"}
        total_score = max(total_score, APPROVE_CEILING + 1)   # >= 40 → STEP_UP
        if len(inj_signals) >= 2 or (strong_injection & set(inj_signals)):
            total_score = max(total_score, DENY_FLOOR)         # >= 75 → DENY
            confidence = max(confidence, CONFIDENCE_FLOOR)     # ensure DENY, not STEP_UP

    # Clamp
    total_score = max(0, min(total_score, 100))
    confidence = max(0.10, min(confidence, 0.99))

    # No signals → safe baseline
    if not all_signals:
        total_score = max(total_score, 5)
        confidence = 0.95

    return RiskAssessment(
        score=total_score,
        band=_score_band(total_score),
        confidence=round(confidence, 2),
        signals=all_signals,
        signal_details=all_details,
    )
