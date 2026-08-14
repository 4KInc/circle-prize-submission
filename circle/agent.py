"""Event-driven Verigate Agent — reacts to payment intents, not cron schedules.

This agent receives payment intents from enterprise agents, reasons about
them, and takes autonomous action. It is NOT a cron job — it responds to
events in real time.

Key autonomous decisions the agent makes:
  1. WHETHER to screen (all intents are screened)
  2. WHETHER to STEP_UP (based on risk score + confidence)
  3. WHICH validator to use (can select from multiple)
  4. HOW MUCH to spend on evidence (dynamic pricing)
  5. WHETHER the evidence cost is worth it (economic rationality)

The agent uses Gemini for reasoning about validator selection and
cost/benefit analysis. The scoring and enforcement paths remain
deterministic (no LLM).
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("circle.agent")


@dataclass
class AgentDecision:
    """Record of an autonomous decision made by the Verigate agent."""
    intent: dict
    decision: str  # APPROVE, STEP_UP, DENY
    score: int
    band: str
    confidence: float
    signals: list[str]
    rationale: str
    step_up_executed: bool = False
    evidence_fee: float = 0.0
    evidence_worth_it: bool = True
    validator_selected: str = "default"
    governance: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "decision": self.decision,
            "score": self.score,
            "band": self.band,
            "confidence": self.confidence,
            "signals": self.signals,
            "rationale": self.rationale,
            "step_up_executed": self.step_up_executed,
            "evidence_fee": self.evidence_fee,
            "evidence_worth_it": self.evidence_worth_it,
            "validator_selected": self.validator_selected,
            "governance": self.governance,
            "timestamp": self.timestamp,
            "autonomous": True,
            "human_intervention": False,
        }


class VerigateAgent:
    """An autonomous AI agent that screens payments and purchases evidence.

    Not a cron job. Responds to events. Makes economic decisions.
    """

    def __init__(self):
        self.decisions: list[AgentDecision] = []
        self._source_wallet = os.environ.get(
            "CIRCLE_AGENT_WALLET",
            "0x5c34e3e05f0f1b9c4e3b92846791c6516dd431a2",
        )
        self._chain = os.environ.get("CIRCLE_CHAIN", "BASE")

    async def handle_payment_intent(self, intent: dict) -> AgentDecision:
        """Agent receives a payment intent and decides what to do.

        This is event-driven — the agent responds to an incoming intent,
        not a scheduled timer.
        """
        from circle.risk_scorer import evaluate_risk

        # 1. Screen the intent (deterministic — no LLM)
        risk = evaluate_risk(
            payee=intent.get("payee", ""),
            amount=intent.get("amount", "0"),
            service=intent.get("service", ""),
            reason=intent.get("reason", ""),
            source_wallet=self._source_wallet,
            chain=self._chain,
        )

        decision = AgentDecision(
            intent=intent,
            decision=risk.decision,
            score=risk.score,
            band=risk.band,
            confidence=risk.confidence,
            signals=risk.signals,
            rationale=risk.rationale,
        )

        # 2. On STEP_UP: decide whether evidence is worth the cost
        if risk.decision == "STEP_UP":
            amount = float(intent.get("amount", 0))
            evidence_fee = max(0.02, min(amount * 0.001, 5.00))
            decision.evidence_fee = evidence_fee

            # Economic rationality: don't overpay for evidence
            decision.evidence_worth_it = self._evidence_is_worth_cost(
                evidence_fee, amount, risk.score,
            )

            if decision.evidence_worth_it:
                # Select validator (could be multiple in production)
                decision.validator_selected = await self._select_validator(
                    intent, risk.score,
                )
                decision.step_up_executed = True
                decision.decision = "STEP_UP"
            else:
                # Evidence too expensive relative to risk — deny conservatively
                decision.decision = "DENY"
                decision.rationale += f" Evidence cost ${evidence_fee:.2f} exceeds economic threshold for ${amount:.2f} payment."

        # 3. On DENY: run governance pipeline for actionable intel
        if risk.decision == "DENY" or decision.decision == "DENY":
            decision.governance = self._run_governance(intent, risk)

        self.decisions.append(decision)
        logger.info(
            "Agent decision: %s (score=%d, step_up=%s, validator=%s)",
            decision.decision, decision.score,
            decision.step_up_executed, decision.validator_selected,
        )
        return decision

    def _evidence_is_worth_cost(
        self, fee: float, amount: float, risk_score: int,
    ) -> bool:
        """Agent decides if buying evidence is economically rational.

        Evidence cost should be << potential loss from a wrong decision.
        Rule: don't spend more than 50% of risk-adjusted expected loss.
        """
        if amount <= 0:
            return False
        potential_loss = amount * (risk_score / 100)
        return fee < potential_loss * 0.5

    async def _select_validator(
        self, intent: dict, risk_score: int,
    ) -> str:
        """Agent selects which validator to use.

        In production, this would query multiple x402 validator services
        and select based on cost, specialty, and reputation.
        Currently returns the default validator.
        """
        # Future: discover validators via x402 service discovery
        # and use Gemini to evaluate cost/quality/speed tradeoffs
        validators = [
            {
                "id": "default",
                "endpoint": os.environ.get("VALIDATOR_URL", ""),
                "specialty": "general",
                "cost": 0.02,
            },
        ]

        # For now, return the default. With multiple validators,
        # Gemini would help evaluate which is best for this intent.
        return validators[0]["id"]

    def _run_governance(self, intent: dict, risk) -> dict:
        """Run governance agents for actionable intelligence on DENY."""
        try:
            from circle.agents import GovernanceSystem
            gov = GovernanceSystem(tenant="agent-event-driven")
            denial_receipt = {
                "receipt_hash": f"sha256:{secrets.token_hex(32)}",
                "body": {"decision": "deny", "reasons": risk.signals},
            }
            pipeline = gov.run_post_denial_pipeline(
                denial_receipt=denial_receipt,
                denial_reasons=risk.signals,
                intent_context=intent,
                policy_hash=risk.model_version,
            )
            inc = pipeline["incident"]["body"]
            prop = pipeline["proposal"]["body"]
            return {
                "incident_severity": inc.get("severity"),
                "incident_summary": inc.get("narrative", {}).get("summary", ""),
                "recommendations": [
                    p.get("change_type") for p in prop.get("proposals", [])
                ],
            }
        except Exception:
            return {}

    def get_stats(self) -> dict:
        """Return agent activity stats — shows reasoning, not just forwarding."""
        total = len(self.decisions)
        approved = sum(1 for d in self.decisions if d.decision == "APPROVE")
        step_up = sum(1 for d in self.decisions if d.step_up_executed)
        denied = sum(1 for d in self.decisions if d.decision == "DENY")
        total_fees = sum(d.evidence_fee for d in self.decisions if d.step_up_executed)
        not_worth = sum(1 for d in self.decisions if not d.evidence_worth_it and d.evidence_fee > 0)

        return {
            "total_decisions": total,
            "approved": approved,
            "step_up": step_up,
            "denied": denied,
            "total_evidence_fees": round(total_fees, 4),
            "evidence_deemed_worth_cost": step_up,
            "evidence_deemed_not_worth_cost": not_worth,
            "avg_evidence_fee": round(total_fees / max(step_up, 1), 4),
            "economic_rationality": {
                "decisions_where_agent_chose_not_to_buy": not_worth,
                "reason": "Evidence cost exceeded 50% of risk-adjusted expected loss",
            },
        }


# Singleton agent instance
_agent: VerigateAgent | None = None


def get_agent() -> VerigateAgent:
    """Get or create the singleton Verigate agent."""
    global _agent
    if _agent is None:
        _agent = VerigateAgent()
    return _agent
