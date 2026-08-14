"""Gemini-mediated evidence scope negotiation between agents.

When an enterprise agent and carrier agent need to agree on what evidence
is shared (scope, retention, purpose), Gemini mediates the negotiation:

  Enterprise: "I need SOC2 audit trail coverage"
  Carrier: "I can provide decision receipts but not raw behavioral signals"
  Gemini: "Proposed scope: decision receipts + anonymized signal summary.
           Both parties' constraints satisfied."

Trust model:
  - Gemini MEDIATES — proposes scope that satisfies both constraints
  - Each agent REVIEWS and SIGNS — consent is cryptographic, not assumed
  - The negotiated scope is ENFORCED by the consent grant system
  - If no consensus, defaults to minimum viable scope (decisions only)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("circle.negotiation")


@dataclass
class EvidenceScope:
    """What evidence is shared between enterprise and carrier."""
    include_decisions: bool = True
    include_risk_scores: bool = True
    include_signal_summary: bool = False   # anonymized signal categories
    include_raw_signals: bool = False       # full signal details
    include_behavioral: bool = False        # behavioral baseline stats
    include_gemini_reasoning: bool = False  # Gemini's evidence analysis
    include_forensic_records: bool = False  # isolation/incident details
    retention_days: int = 90
    purpose: str = "underwriting"

    def to_dict(self) -> dict:
        return {
            "include_decisions": self.include_decisions,
            "include_risk_scores": self.include_risk_scores,
            "include_signal_summary": self.include_signal_summary,
            "include_raw_signals": self.include_raw_signals,
            "include_behavioral": self.include_behavioral,
            "include_gemini_reasoning": self.include_gemini_reasoning,
            "include_forensic_records": self.include_forensic_records,
            "retention_days": self.retention_days,
            "purpose": self.purpose,
        }


@dataclass
class NegotiationRound:
    """One round of negotiation between enterprise and carrier."""
    round_number: int
    enterprise_position: str
    carrier_position: str
    gemini_proposal: str
    proposed_scope: EvidenceScope
    consensus: bool = False
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "round": self.round_number,
            "enterprise_position": self.enterprise_position,
            "carrier_position": self.carrier_position,
            "gemini_proposal": self.gemini_proposal,
            "proposed_scope": self.proposed_scope.to_dict(),
            "consensus": self.consensus,
            "timestamp": self.timestamp,
        }


# Gemini schema for negotiation output
_NEGOTIATION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "proposal": {"type": "STRING"},
        "include_decisions": {"type": "BOOLEAN"},
        "include_risk_scores": {"type": "BOOLEAN"},
        "include_signal_summary": {"type": "BOOLEAN"},
        "include_raw_signals": {"type": "BOOLEAN"},
        "include_behavioral": {"type": "BOOLEAN"},
        "include_gemini_reasoning": {"type": "BOOLEAN"},
        "include_forensic_records": {"type": "BOOLEAN"},
        "retention_days": {"type": "INTEGER"},
        "consensus_reached": {"type": "BOOLEAN"},
        "reasoning": {"type": "STRING"},
    },
    "required": ["proposal", "consensus_reached", "reasoning"],
}


def negotiate_evidence_scope(
    enterprise_needs: str,
    carrier_constraints: str,
    prior_rounds: list[NegotiationRound] | None = None,
) -> NegotiationRound:
    """Gemini mediates evidence scope between enterprise and carrier agents.

    Returns a NegotiationRound with a proposed scope that attempts to
    satisfy both parties' requirements.
    """
    round_num = len(prior_rounds or []) + 1
    prior = prior_rounds or []

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return _fallback_round(round_num, enterprise_needs, carrier_constraints)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prior_text = ""
        if prior:
            prior_text = "\n\nPRIOR ROUNDS:\n" + "\n".join(
                f"Round {r.round_number}: Enterprise: {r.enterprise_position} | "
                f"Carrier: {r.carrier_position} | Proposal: {r.gemini_proposal}"
                for r in prior
            )

        prompt = f"""Two AI agents are negotiating evidence scope for an insurance proof bundle.

ENTERPRISE AGENT NEEDS: "{enterprise_needs}"
CARRIER AGENT CONSTRAINTS: "{carrier_constraints}"
{prior_text}

ROUND {round_num}: Find a scope that satisfies both parties. Rules:
1. Decisions and risk scores are always included (minimum viable scope)
2. Raw signals require explicit enterprise consent
3. Behavioral data requires explicit enterprise consent
4. Retention cannot exceed 365 days
5. If the enterprise asks for "full audit" or "SOC2", include signal summary + forensic records
6. If the carrier says "no raw data", exclude raw_signals and behavioral
7. Set consensus_reached=true only if both positions can be fully satisfied
8. Be specific about what's included and why"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_NEGOTIATION_SCHEMA,
            ),
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text)

        scope = EvidenceScope(
            include_decisions=True,  # always
            include_risk_scores=True,  # always
            include_signal_summary=data.get("include_signal_summary", False),
            include_raw_signals=data.get("include_raw_signals", False),
            include_behavioral=data.get("include_behavioral", False),
            include_gemini_reasoning=data.get("include_gemini_reasoning", False),
            include_forensic_records=data.get("include_forensic_records", False),
            retention_days=min(365, max(30, data.get("retention_days", 90))),
            purpose="underwriting",
        )

        return NegotiationRound(
            round_number=round_num,
            enterprise_position=enterprise_needs,
            carrier_position=carrier_constraints,
            gemini_proposal=data.get("proposal", ""),
            proposed_scope=scope,
            consensus=data.get("consensus_reached", False),
        )

    except Exception as e:
        logger.warning("Negotiation Gemini call failed: %s", e)
        return _fallback_round(round_num, enterprise_needs, carrier_constraints)


def _fallback_round(
    round_num: int, enterprise: str, carrier: str,
) -> NegotiationRound:
    """Conservative fallback: minimum viable scope."""
    return NegotiationRound(
        round_number=round_num,
        enterprise_position=enterprise,
        carrier_position=carrier,
        gemini_proposal="Gemini unavailable. Defaulting to minimum viable scope: decisions + risk scores only.",
        proposed_scope=EvidenceScope(),  # defaults: decisions + risk scores
        consensus=False,
    )
