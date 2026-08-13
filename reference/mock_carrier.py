"""Reference mock carrier agent — demo only, replace with your own.

This exercises the full Verigate evidence rail from outside the core:
1. Subscribe to decision events (B2)
2. Check consent grant (B3)
3. Pay x402 to pull evidence bundle (B4)
4. Verify the bundle
5. Fill the feedback schema with a trivial deterministic stub assessment
6. Sign and post back via the feedback channel (B5)

Verigate authors NO carrier assessment. This stub assessment is
explicitly not real underwriting — it's a deterministic function of
the risk score that exists only to exercise the schema.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from circle.evidence_rails import (
    CarrierFeedback,
    ConsentGrant,
    DecisionEvent,
    EventEmitter,
    FeedbackChannel,
    ConsentRegistry,
    EvidenceAuditLog,
    CARRIER_PULL_FEE_USDC,
)

logger = logging.getLogger("reference.mock_carrier")

CARRIER_ID = "reference-carrier-demo"


class MockCarrierAgent:
    """Reference carrier agent that exercises Verigate's evidence rails.

    THIS IS A DEMO STUB. Replace with real carrier integration.
    Verigate provides the rails and format, not this decision.
    """

    def __init__(
        self,
        carrier_id: str = CARRIER_ID,
        emitter: EventEmitter | None = None,
        consent_registry: ConsentRegistry | None = None,
        feedback_channel: FeedbackChannel | None = None,
        audit_log: EvidenceAuditLog | None = None,
    ):
        self.carrier_id = carrier_id
        self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._emitter = emitter
        self._consent = consent_registry
        self._feedback = feedback_channel
        self._audit = audit_log
        self._processed_events: list[str] = []

        # Register with the feedback channel
        if self._feedback:
            self._feedback.register_carrier_key(self.carrier_id, self._public_key)

        # Subscribe to events
        if self._emitter:
            self._emitter.subscribe(self._on_event)

    def _on_event(self, event: DecisionEvent) -> None:
        """Handle a decision event from Verigate."""
        if event.event_type not in ("denial", "high_severity", "breaker_tripped"):
            return

        logger.info("Carrier received event: %s (severity=%s, score=%d)",
                     event.event_type, event.severity, event.score)

        # Check consent grant
        if self._consent:
            grant = self._consent.check_grant(
                carrier_id=self.carrier_id,
                wallet=event.wallet,
                purpose="underwriting",
            )
            if not grant:
                logger.warning("No valid consent grant for wallet %s", event.wallet)
                return
        else:
            grant = None

        self._processed_events.append(event.event_id)

        # In production: pay x402 to pull the bundle here.
        # For the reference mock, we simulate the pull and generate feedback.
        assessment = self._stub_assessment(event)

        # Sign and post feedback
        feedback = self._build_feedback(event, assessment)

        if self._feedback:
            result = self._feedback.verify_and_relay(feedback)
            logger.info("Feedback relay result: %s", result.get("status"))

            if self._audit:
                self._audit.log_delivery(
                    carrier_id=self.carrier_id,
                    feedback_id=feedback.feedback_id,
                    event_ref=event.event_id,
                    signature_status=result.get("status", "unknown"),
                )

    def _stub_assessment(self, event: DecisionEvent) -> dict:
        """Trivial deterministic stub — NOT real underwriting.

        This is a placeholder that maps risk score to a simple category.
        A real carrier would run their own models, consult their own data,
        and produce their own assessment. Verigate does not compute this.
        """
        if event.score >= 90:
            action = "flag_for_review"
            note = "Score exceeds carrier threshold; manual review recommended"
        elif event.score >= 75:
            action = "monitor"
            note = "Elevated risk; increase monitoring frequency"
        else:
            action = "acknowledge"
            note = "Within acceptable parameters"

        return {
            "_stub": True,
            "_notice": "Reference mock assessment — replace with real carrier logic",
            "action": action,
            "note": note,
            "score_observed": event.score,
            "signals_observed": event.signals,
        }

    def _build_feedback(self, event: DecisionEvent, assessment: dict) -> CarrierFeedback:
        """Build and sign a feedback message."""
        feedback_id = f"fb_{secrets.token_hex(8)}"
        timestamp = datetime.now(timezone.utc).isoformat()

        feedback = CarrierFeedback(
            feedback_id=feedback_id,
            carrier_id=self.carrier_id,
            event_ref=event.event_id,
            subject_wallet=event.wallet,
            assessment=assessment,
            timestamp=timestamp,
            signature="",
        )

        # Sign
        payload = json.dumps({
            "feedback_id": feedback.feedback_id,
            "carrier_id": feedback.carrier_id,
            "event_ref": feedback.event_ref,
            "subject_wallet": feedback.subject_wallet,
            "assessment": feedback.assessment,
            "timestamp": feedback.timestamp,
        }, sort_keys=True, separators=(",", ":")).encode()
        feedback.signature = self._private_key.sign(payload).hex()

        return feedback

    def process_event_manually(self, event: DecisionEvent) -> dict:
        """Process an event outside the subscription path (for testing/demo)."""
        self._on_event(event)
        return {
            "carrier_id": self.carrier_id,
            "event_id": event.event_id,
            "processed": event.event_id in self._processed_events,
        }

    @property
    def processed_events(self) -> list[str]:
        return list(self._processed_events)
