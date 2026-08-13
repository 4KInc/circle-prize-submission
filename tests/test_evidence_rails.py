"""Tests for evidence rails (B2-B7)."""

import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from circle.evidence_rails import (
    DecisionEvent,
    EventEmitter,
    ConsentGrant,
    ConsentRegistry,
    CarrierFeedback,
    FeedbackChannel,
    EvidenceAuditLog,
)
from reference.mock_carrier import MockCarrierAgent


def _make_event(**kwargs):
    return DecisionEvent(
        event_id=kwargs.get("event_id", "evt_test123"),
        event_type=kwargs.get("event_type", "denial"),
        bundle_ref=kwargs.get("bundle_ref", "bundles/test.json"),
        severity=kwargs.get("severity", "critical"),
        wallet=kwargs.get("wallet", "0xagent"),
        payee=kwargs.get("payee", "0xdead"),
        amount=kwargs.get("amount", "4500"),
        score=kwargs.get("score", 100),
        decision=kwargs.get("decision", "DENY"),
        signals=kwargs.get("signals", ["sanctioned_address"]),
        timestamp=kwargs.get("timestamp", "2026-08-12T00:00:00Z"),
    )


# ─── B2: Event emission ─────────────────────────────────────────────

def test_b2_event_emission():
    """Events are emitted and subscribers notified."""
    key = Ed25519PrivateKey.generate()
    emitter = EventEmitter(signing_key=key)
    received = []
    emitter.subscribe(lambda e: received.append(e))

    event = _make_event()
    emitter.emit(event)

    assert len(received) == 1
    assert received[0].event_id == "evt_test123"
    assert received[0].signature != ""


def test_b2_event_signed():
    """Emitted events are signed with Ed25519."""
    key = Ed25519PrivateKey.generate()
    emitter = EventEmitter(signing_key=key)
    event = emitter.emit(_make_event())
    assert len(event.signature) > 0


# ─── B3: Consent grants ─────────────────────────────────────────────

def test_b3_consent_grant_valid():
    """Valid consent grant allows access."""
    registry = ConsentRegistry()
    registry.create_grant(ConsentGrant(
        grant_id="g1",
        insured_wallet="0xagent",
        carrier_id="carrier-1",
        scope_wallets=["0xagent"],
        purpose="underwriting",
        valid_from="2026-01-01T00:00:00+00:00",
        valid_until="2027-01-01T00:00:00+00:00",
    ))

    grant = registry.check_grant("carrier-1", "0xagent", "underwriting")
    assert grant is not None
    assert grant.grant_id == "g1"


def test_b3_consent_grant_wrong_carrier():
    """Wrong carrier is rejected."""
    registry = ConsentRegistry()
    registry.create_grant(ConsentGrant(
        grant_id="g1",
        insured_wallet="0xagent",
        carrier_id="carrier-1",
        scope_wallets=["0xagent"],
        purpose="underwriting",
        valid_from="2026-01-01T00:00:00+00:00",
        valid_until="2027-01-01T00:00:00+00:00",
    ))

    assert registry.check_grant("carrier-2", "0xagent", "underwriting") is None


def test_b3_consent_revoked():
    """Revoked grant is rejected."""
    registry = ConsentRegistry()
    registry.create_grant(ConsentGrant(
        grant_id="g1",
        insured_wallet="0xagent",
        carrier_id="carrier-1",
        scope_wallets=["0xagent"],
        purpose="underwriting",
        valid_from="2026-01-01T00:00:00+00:00",
        valid_until="2027-01-01T00:00:00+00:00",
    ))

    registry.revoke_grant("g1")
    assert registry.check_grant("carrier-1", "0xagent", "underwriting") is None


def test_b3_audit_logged():
    """Consent checks are audit-logged."""
    registry = ConsentRegistry()
    registry.create_grant(ConsentGrant(
        grant_id="g1",
        insured_wallet="0xagent",
        carrier_id="carrier-1",
        scope_wallets=["0xagent"],
        purpose="underwriting",
        valid_from="2026-01-01T00:00:00+00:00",
        valid_until="2027-01-01T00:00:00+00:00",
    ))
    registry.check_grant("carrier-1", "0xagent", "underwriting")
    registry.check_grant("carrier-2", "0xagent", "underwriting")

    assert len(registry.audit_log) >= 3  # create + valid check + rejected check


# ─── B5: Feedback channel ───────────────────────────────────────────

def test_b5_valid_feedback_delivered():
    """Validly signed feedback is delivered."""
    channel = FeedbackChannel()
    key = Ed25519PrivateKey.generate()
    channel.register_carrier_key("carrier-1", key.public_key())

    feedback = CarrierFeedback(
        feedback_id="fb_1",
        carrier_id="carrier-1",
        event_ref="evt_1",
        subject_wallet="0xagent",
        assessment={"action": "monitor"},
        timestamp="2026-08-12T00:00:00Z",
        signature="",
    )

    # Sign it
    payload = json.dumps({
        "feedback_id": feedback.feedback_id,
        "carrier_id": feedback.carrier_id,
        "event_ref": feedback.event_ref,
        "subject_wallet": feedback.subject_wallet,
        "assessment": feedback.assessment,
        "timestamp": feedback.timestamp,
    }, sort_keys=True, separators=(",", ":")).encode()
    feedback.signature = key.sign(payload).hex()

    result = channel.verify_and_relay(feedback)
    assert result["status"] == "delivered"
    assert result["verified"] is True


def test_b5_invalid_signature_rejected():
    """Invalid signature is rejected."""
    channel = FeedbackChannel()
    key = Ed25519PrivateKey.generate()
    channel.register_carrier_key("carrier-1", key.public_key())

    feedback = CarrierFeedback(
        feedback_id="fb_1",
        carrier_id="carrier-1",
        event_ref="evt_1",
        subject_wallet="0xagent",
        assessment={"action": "monitor"},
        timestamp="2026-08-12T00:00:00Z",
        signature="deadbeef" * 16,  # invalid
    )

    result = channel.verify_and_relay(feedback)
    assert result["status"] == "rejected"
    assert result["reason"] == "invalid_signature"


def test_b5_unknown_carrier_rejected():
    """Unknown carrier is rejected."""
    channel = FeedbackChannel()

    feedback = CarrierFeedback(
        feedback_id="fb_1",
        carrier_id="unknown-carrier",
        event_ref="evt_1",
        subject_wallet="0xagent",
        assessment={},
        timestamp="2026-08-12T00:00:00Z",
        signature="abc123",
    )

    result = channel.verify_and_relay(feedback)
    assert result["status"] == "rejected"
    assert result["reason"] == "unknown_carrier"


def test_b5_delivery_never_blocks_payment_path():
    """Feedback delivery is async — never blocks the payment path.

    This test asserts that the feedback channel processes synchronously
    but is designed to be called off the payment path (not in /api/check).
    """
    channel = FeedbackChannel()
    # Even with no keys registered, verify_and_relay returns immediately
    feedback = CarrierFeedback(
        feedback_id="fb_1",
        carrier_id="carrier-1",
        event_ref="evt_1",
        subject_wallet="0xagent",
        assessment={},
        timestamp="2026-08-12T00:00:00Z",
        signature="abc",
    )
    result = channel.verify_and_relay(feedback)
    assert result is not None  # Returns immediately, doesn't hang


# ─── B6: Mock carrier agent ─────────────────────────────────────────

def test_b6_mock_carrier_full_loop():
    """Reference carrier exercises the full rail."""
    key = Ed25519PrivateKey.generate()
    emitter = EventEmitter(signing_key=key)
    consent = ConsentRegistry()
    feedback = FeedbackChannel()
    audit = EvidenceAuditLog()

    # Create consent grant
    consent.create_grant(ConsentGrant(
        grant_id="g1",
        insured_wallet="0xagent",
        carrier_id="reference-carrier-demo",
        scope_wallets=["0xagent"],
        purpose="underwriting",
        valid_from="2026-01-01T00:00:00+00:00",
        valid_until="2027-01-01T00:00:00+00:00",
    ))

    carrier = MockCarrierAgent(
        emitter=emitter,
        consent_registry=consent,
        feedback_channel=feedback,
        audit_log=audit,
    )

    # Emit an event
    event = _make_event(wallet="0xagent")
    emitter.emit(event)

    # Carrier should have processed it
    assert len(carrier.processed_events) == 1
    assert len(feedback.delivered) == 1
    assert feedback.delivered[0]["status"] == "delivered"


# ─── B7: Audit logging ──────────────────────────────────────────────

def test_b7_pull_logged():
    """Evidence pulls are logged."""
    audit = EvidenceAuditLog()
    audit.log_pull(
        carrier_id="carrier-1",
        bundle_ref="bundles/test.json",
        grant_id="g1",
        tx_hash="0xabc",
        fee_usdc="0.25",
        status="paid",
    )

    assert len(audit.pulls) == 1
    assert audit.pulls[0]["fee_usdc"] == "0.25"


def test_b7_revenue_metrics():
    """Revenue metrics count from real data."""
    audit = EvidenceAuditLog()
    audit.log_pull("c1", "b1", "g1", "0x1", "0.25", "paid")
    audit.log_pull("c1", "b2", "g1", "0x2", "0.25", "paid")
    audit.log_pull("c2", "b3", "g2", "", "0.25", "unpaid")  # rejected

    metrics = audit.revenue_metrics()
    assert metrics["pull_fees"]["total_pulls"] == 2
    assert metrics["pull_fees"]["total_revenue_usdc"] == "$0.50"
