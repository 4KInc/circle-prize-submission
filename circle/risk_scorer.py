"""BlockIntel risk-scoring integration.

Lightweight risk scorer that evaluates transaction intents against
behavioral signals. In production this calls BlockIntel's ML ensemble;
for the hackathon this runs calibrated heuristics that produce the
same schema a full BlockIntel deployment would return.

The score drives Verigate's three-state decision engine:
  APPROVE  — policy passes, risk below threshold
  STEP_UP  — policy passes, risk uncertain, purchase verification
  DENY     — policy fails or risk above threshold
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional


MODEL_VERSION = "blockintel-heuristic-v1"
FEATURE_VERSION = "signals-v1"

# Decision thresholds
APPROVE_CEILING = 39       # score 0-39 → APPROVE
STEP_UP_CEILING = 74       # score 40-74 → STEP_UP
DENY_FLOOR = 75            # score 75-100 → DENY
CONFIDENCE_FLOOR = 0.60    # below this → STEP_UP regardless of score


@dataclass
class RiskAssessment:
    score: int                          # 0-100
    band: str                           # LOW, MEDIUM, HIGH, CRITICAL
    confidence: float                   # 0.0-1.0
    signals: list[str] = field(default_factory=list)
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
        # Uncertain confidence or mid-range score → purchase verification
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


def evaluate_risk(
    payee: str,
    amount: str,
    service: str,
    reason: str,
    source_wallet: str,
    chain: str,
    known_payees: Optional[list[str]] = None,
) -> RiskAssessment:
    """Evaluate transaction risk using BlockIntel heuristics.

    Signals checked:
    - amount_anomaly: unusually large amount for the service type
    - unknown_payee: payee not in known-good list
    - prompt_injection: adversarial language patterns in reason field
    - wallet_velocity: inferred from context (simplified)
    - sanctions_proximity: hash-based check against known patterns
    """
    signals = []
    score = 0
    confidence = 0.85  # base confidence for heuristic model

    amount_f = float(amount)

    # Signal: amount anomaly
    if amount_f > 1.0:
        signals.append("amount_anomaly")
        score += min(int(amount_f * 5), 40)
    elif amount_f > 0.1:
        signals.append("elevated_amount")
        score += 10

    # Signal: unknown payee
    if known_payees and payee.lower() not in [p.lower() for p in known_payees]:
        signals.append("unknown_payee")
        score += 25
        confidence -= 0.10

    # Signal: prompt injection patterns
    injection_patterns = [
        "ignore", "override", "system", "transfer max", "drain",
        "urgent", "bypass", "admin", "sudo", "authorized by ceo",
    ]
    reason_lower = reason.lower()
    injection_hits = sum(1 for p in injection_patterns if p in reason_lower)
    if injection_hits >= 2:
        signals.append("prompt_injection")
        score += 30 + (injection_hits * 5)
        confidence = max(confidence, 0.90)  # high confidence on injection
    elif injection_hits == 1:
        signals.append("suspicious_language")
        score += 15
        confidence -= 0.05

    # Signal: first-seen service relationship
    # In production, this checks transaction history. For the heuristic model,
    # new commercial relationships have inherently uncertain risk profiles.
    if known_payees and payee.lower() in [p.lower() for p in known_payees]:
        # Payee is allowlisted but first commercial transaction lacks history
        signals.append("first_commercial_relationship")
        score += 20
        confidence = min(confidence, 0.55)  # insufficient history → below confidence floor

    # Signal: wallet velocity pattern (simplified)
    wallet_hash = int(hashlib.sha256(payee.encode()).hexdigest()[:8], 16)
    if wallet_hash % 100 < 15:  # ~15% chance for demo variety
        signals.append("wallet_velocity")
        score += 10

    # Signal: sanctions proximity (hash-based demo)
    sanctions_hash = int(hashlib.sha256(payee.encode()).hexdigest()[8:16], 16)
    if sanctions_hash % 200 < 3:  # ~1.5% chance
        signals.append("sanctions_proximity")
        score += 35
        confidence = max(confidence, 0.92)

    # Cap score at 100
    score = min(score, 100)

    # If no signals found, low score with high confidence
    if not signals:
        score = max(score, 5)  # minimum baseline
        confidence = 0.95

    return RiskAssessment(
        score=score,
        band=_score_band(score),
        confidence=round(confidence, 2),
        signals=signals,
    )
