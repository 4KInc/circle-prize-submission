"""Evidence rails: events, consent grants, paid proof-pull, feedback channel.

P1 — Verigate owns the rails, schema, and monetized endpoints.
The carrier agent is external; only a reference mock lives in this repo.

B2: Decision-event emission
B3: Consent grant stub
B4: x402-paid proof-pull (see server endpoint)
B5: Signed feedback channel
B7: Audit logging
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

logger = logging.getLogger("circle.evidence_rails")

# Config constant for carrier pull fee (B4)
CARRIER_PULL_FEE_USDC = os.environ.get("CARRIER_PULL_FEE_USDC", "0.25")


# ─── B2: Decision Events ────────────────────────────────────────────

@dataclass
class DecisionEvent:
    """Signed event emitted on DENY, high-severity, or breaker trip."""
    event_id: str
    event_type: str  # "denial", "breaker_tripped", "high_severity"
    bundle_ref: str  # GCS path or hash of the proof bundle
    severity: str  # "low", "medium", "high", "critical"
    wallet: str
    payee: str
    amount: str
    score: int
    decision: str
    signals: list[str]
    timestamp: str
    signature: str = ""


class EventEmitter:
    """Emits signed decision events on a subscribable channel."""

    def __init__(self, signing_key: Ed25519PrivateKey | None = None):
        self._subscribers: list[callable] = []
        self._events: list[DecisionEvent] = []
        self._signing_key = signing_key

    def subscribe(self, callback: callable) -> None:
        self._subscribers.append(callback)

    def emit(self, event: DecisionEvent) -> DecisionEvent:
        """Sign and emit an event to all subscribers."""
        if self._signing_key:
            payload = json.dumps({
                "event_id": event.event_id,
                "event_type": event.event_type,
                "bundle_ref": event.bundle_ref,
                "severity": event.severity,
                "wallet": event.wallet,
                "score": event.score,
                "decision": event.decision,
                "timestamp": event.timestamp,
            }, sort_keys=True, separators=(",", ":")).encode()
            event.signature = self._signing_key.sign(payload).hex()

        self._events.append(event)
        for cb in self._subscribers:
            try:
                cb(event)
            except Exception as e:
                logger.warning("Event subscriber error: %s", e)

        logger.info("Event emitted: %s severity=%s score=%d",
                     event.event_type, event.severity, event.score)
        return event

    @property
    def events(self) -> list[DecisionEvent]:
        return list(self._events)


# ─── B3: Consent Grants ─────────────────────────────────────────────

@dataclass
class ConsentGrant:
    """Insured pre-authorizes a named carrier to pull evidence."""
    grant_id: str
    insured_wallet: str  # the enterprise agent's wallet
    carrier_id: str  # carrier's registered ID
    scope_wallets: list[str]  # which agent wallets the carrier can query
    purpose: str  # "underwriting", "renewal", "claims"
    valid_from: str  # ISO timestamp
    valid_until: str  # ISO timestamp
    created_at: str = ""
    revoked: bool = False


class ConsentRegistry:
    """Manages consent grants for carrier evidence access."""

    def __init__(self):
        self._grants: dict[str, ConsentGrant] = {}
        self._audit_log: list[dict] = []

    def create_grant(self, grant: ConsentGrant) -> ConsentGrant:
        if not grant.created_at:
            grant.created_at = datetime.now(timezone.utc).isoformat()
        self._grants[grant.grant_id] = grant
        self._log("grant_created", grant.grant_id, grant.carrier_id, "success")
        logger.info("Consent grant created: %s for carrier %s",
                     grant.grant_id, grant.carrier_id)
        return grant

    def check_grant(
        self, carrier_id: str, wallet: str, purpose: str,
    ) -> ConsentGrant | None:
        """Check if a valid grant exists for this carrier/wallet/purpose."""
        now = datetime.now(timezone.utc).isoformat()
        for grant in self._grants.values():
            if grant.revoked:
                continue
            if grant.carrier_id != carrier_id:
                continue
            if wallet not in grant.scope_wallets:
                continue
            if purpose and grant.purpose != purpose:
                continue
            if grant.valid_from > now or grant.valid_until < now:
                continue
            self._log("grant_checked", grant.grant_id, carrier_id, "valid")
            return grant

        self._log("grant_checked", "none", carrier_id, "rejected")
        return None

    def revoke_grant(self, grant_id: str) -> bool:
        grant = self._grants.get(grant_id)
        if grant:
            grant.revoked = True
            self._log("grant_revoked", grant_id, grant.carrier_id, "revoked")
            return True
        return False

    def _log(self, action: str, grant_id: str, carrier_id: str, result: str) -> None:
        self._audit_log.append({
            "action": action,
            "grant_id": grant_id,
            "carrier_id": carrier_id,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @property
    def audit_log(self) -> list[dict]:
        return list(self._audit_log)


# ─── B5: Signed Feedback Channel ────────────────────────────────────

@dataclass
class CarrierFeedback:
    """Feedback message from a carrier, delivered over Verigate's channel.

    Verigate verifies the signature and relays; it does NOT interpret
    or compute the assessment. The assessment blob is opaque.
    """
    feedback_id: str
    carrier_id: str
    event_ref: str  # the event_id this feedback responds to
    subject_wallet: str
    assessment: dict  # opaque blob filled by the carrier
    timestamp: str
    signature: str  # carrier's Ed25519 signature over the canonical payload


class FeedbackChannel:
    """Receives carrier-signed feedback, verifies, and relays to enterprise agents."""

    def __init__(self):
        # carrier_id -> public key
        self._registered_keys: dict[str, Ed25519PublicKey] = {}
        self._delivered: list[dict] = []
        self._rejected: list[dict] = []

    def register_carrier_key(self, carrier_id: str, public_key: Ed25519PublicKey) -> None:
        self._registered_keys[carrier_id] = public_key
        logger.info("Carrier key registered: %s", carrier_id)

    def _canonical_payload(self, fb: CarrierFeedback) -> bytes:
        return json.dumps({
            "feedback_id": fb.feedback_id,
            "carrier_id": fb.carrier_id,
            "event_ref": fb.event_ref,
            "subject_wallet": fb.subject_wallet,
            "assessment": fb.assessment,
            "timestamp": fb.timestamp,
        }, sort_keys=True, separators=(",", ":")).encode()

    def verify_and_relay(self, feedback: CarrierFeedback) -> dict:
        """Verify carrier signature and relay to the enterprise agent.

        Returns delivery record. Never blocks the payment path.
        """
        pub_key = self._registered_keys.get(feedback.carrier_id)
        if pub_key is None:
            record = {
                "feedback_id": feedback.feedback_id,
                "carrier_id": feedback.carrier_id,
                "status": "rejected",
                "reason": "unknown_carrier",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._rejected.append(record)
            logger.warning("Feedback rejected: unknown carrier %s", feedback.carrier_id)
            return record

        # Verify signature
        try:
            payload = self._canonical_payload(feedback)
            pub_key.verify(bytes.fromhex(feedback.signature), payload)
        except Exception:
            record = {
                "feedback_id": feedback.feedback_id,
                "carrier_id": feedback.carrier_id,
                "status": "rejected",
                "reason": "invalid_signature",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._rejected.append(record)
            logger.warning("Feedback rejected: invalid signature from %s", feedback.carrier_id)
            return record

        # Signature valid — relay
        record = {
            "feedback_id": feedback.feedback_id,
            "carrier_id": feedback.carrier_id,
            "event_ref": feedback.event_ref,
            "subject_wallet": feedback.subject_wallet,
            "assessment": feedback.assessment,
            "status": "delivered",
            "verified": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._delivered.append(record)
        logger.info("Feedback delivered: %s from carrier %s",
                     feedback.feedback_id, feedback.carrier_id)
        return record

    @property
    def delivered(self) -> list[dict]:
        return list(self._delivered)

    @property
    def rejected(self) -> list[dict]:
        return list(self._rejected)


# ─── B7: Audit Logging ──────────────────────────────────────────────

class EvidenceAuditLog:
    """Tracks all pull + delivery events with revenue metrics."""

    def __init__(self):
        self._pulls: list[dict] = []
        self._deliveries: list[dict] = []

    def log_pull(
        self, carrier_id: str, bundle_ref: str, grant_id: str,
        tx_hash: str, fee_usdc: str, status: str,
    ) -> dict:
        record = {
            "type": "evidence_pull",
            "carrier_id": carrier_id,
            "bundle_ref": bundle_ref,
            "grant_id": grant_id,
            "tx_hash": tx_hash,
            "fee_usdc": fee_usdc,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._pulls.append(record)
        return record

    def log_delivery(
        self, carrier_id: str, feedback_id: str, event_ref: str,
        signature_status: str,
    ) -> dict:
        record = {
            "type": "feedback_delivery",
            "carrier_id": carrier_id,
            "feedback_id": feedback_id,
            "event_ref": event_ref,
            "signature_status": signature_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._deliveries.append(record)
        return record

    def revenue_metrics(self) -> dict:
        """Two revenue surfaces counted from actual data."""
        successful_pulls = [p for p in self._pulls if p["status"] == "paid"]
        pull_revenue = sum(float(p["fee_usdc"]) for p in successful_pulls)
        return {
            "check_fees": {
                "description": "Enterprise agent pays per screening (Product 1)",
                "fee_per_check": "$0.05",
                "note": "Tracked in treasury transactions",
            },
            "pull_fees": {
                "description": "Carrier agent pays per evidence pull (Product 2)",
                "fee_per_pull": f"${CARRIER_PULL_FEE_USDC}",
                "total_pulls": len(successful_pulls),
                "total_revenue_usdc": f"${pull_revenue:.2f}",
                "note": "5x the check fee — the proof is the product",
            },
        }

    @property
    def pulls(self) -> list[dict]:
        return list(self._pulls)

    @property
    def deliveries(self) -> list[dict]:
        return list(self._deliveries)


# ─── Module singletons ──────────────────────────────────────────────

_emitter: EventEmitter | None = None
_consent: ConsentRegistry | None = None
_feedback: FeedbackChannel | None = None
_audit: EvidenceAuditLog | None = None


def get_emitter(signing_key: Ed25519PrivateKey | None = None) -> EventEmitter:
    global _emitter
    if _emitter is None:
        _emitter = EventEmitter(signing_key)
    return _emitter


def get_consent_registry() -> ConsentRegistry:
    global _consent
    if _consent is None:
        _consent = ConsentRegistry()
    return _consent


def get_feedback_channel() -> FeedbackChannel:
    global _feedback
    if _feedback is None:
        _feedback = FeedbackChannel()
    return _feedback


def get_audit_log() -> EvidenceAuditLog:
    global _audit
    if _audit is None:
        _audit = EvidenceAuditLog()
    return _audit
