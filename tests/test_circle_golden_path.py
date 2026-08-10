"""Unit and integration tests for the Circle golden path.

Tests:
1. Policy evaluation (approve/deny paths)
2. Payment intent digest binding (deterministic, canonical)
3. Replay/nonce+JTI blocking
4. Deny path produces signed denial receipt
5. Per-tenant key isolation
6. Isolator severity classification
7. Receipt chain integrity
8. Merkle inclusion proofs
"""

from __future__ import annotations

import os
import sys

import pytest

# Add engine and project root to path
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
ENGINE_PATH = os.path.join(PROJECT_ROOT, "engine")
sys.path.insert(0, PROJECT_ROOT)
if os.path.isdir(ENGINE_PATH):
    sys.path.insert(0, ENGINE_PATH)

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from gateway.merkle import compute_inclusion_proof, compute_unified_root
from gateway.policy import Policy, PolicyEngine, PolicyRule
from gateway.receipts import ReceiptChain
from gateway.tokens import issue_token, verify_token
from gateway.verify import verify_chain

from circle.executor import PaymentExecutor, PaymentIntent
from circle.isolator import Isolator, classify_severity

# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def private_key():
    return Ed25519PrivateKey.generate()


@pytest.fixture
def receipt_chain(private_key):
    return ReceiptChain(
        tenant="test-tenant",
        private_key=private_key,
        kid="test-kid-001",
    )


@pytest.fixture
def payment_policy():
    return Policy(
        version="payment-v1",
        rules=[
            PolicyRule(id="actions", type="allowlist",
                       config={"allowed_actions": ["pay", "transfer"]}),
            PolicyRule(id="scope", type="resource_scope",
                       config={"allowed_resources": ["0xallowed"]}),
            PolicyRule(id="rate", type="rate_limit",
                       config={"max_actions": 3, "window_seconds": 60}),
        ],
    )


# ── 1. Policy evaluation ─────────────────────────────────────────────

class TestPolicyEvaluation:
    def test_approve_valid_payment(self, payment_policy):
        engine = PolicyEngine(payment_policy)
        result = engine.evaluate("agent-1", "pay", "0xallowed")
        assert result.decision == "approve"
        assert result.reason_codes == []

    def test_deny_unknown_action(self, payment_policy):
        engine = PolicyEngine(payment_policy)
        result = engine.evaluate("agent-1", "delete", "0xallowed")
        assert result.decision == "deny"
        assert any("ACTION_NOT_ALLOWED" in r for r in result.reason_codes)

    def test_deny_off_allowlist_payee(self, payment_policy):
        engine = PolicyEngine(payment_policy)
        result = engine.evaluate("agent-1", "pay", "0xattacker")
        assert result.decision == "deny"
        assert any("RESOURCE_OUT_OF_SCOPE" in r for r in result.reason_codes)

    def test_deny_rate_limit(self, payment_policy):
        engine = PolicyEngine(payment_policy)
        for _ in range(3):
            result = engine.evaluate("agent-1", "pay", "0xallowed")
            assert result.decision == "approve"
        result = engine.evaluate("agent-1", "pay", "0xallowed")
        assert result.decision == "deny"
        assert any("RATE_LIMIT_EXCEEDED" in r for r in result.reason_codes)


# ── 2. Payment intent digest binding ─────────────────────────────────

class TestIntentDigest:
    def test_deterministic_digest(self):
        """Same inputs always produce the same digest."""
        from circle.executor import PaymentExecutor
        key = Ed25519PrivateKey.generate()
        exec1 = PaymentExecutor.__new__(PaymentExecutor)
        digest1 = PaymentExecutor.compute_intent_digest(exec1, PaymentIntent(
            payee="0xABC", amount="1.00", service="svc", reason="test", chain="BASE-SEPOLIA",
        ))
        digest2 = PaymentExecutor.compute_intent_digest(exec1, PaymentIntent(
            payee="0xABC", amount="1.00", service="svc", reason="test", chain="BASE-SEPOLIA",
        ))
        assert digest1 == digest2

    def test_different_payee_different_digest(self):
        exec1 = PaymentExecutor.__new__(PaymentExecutor)
        d1 = PaymentExecutor.compute_intent_digest(exec1, PaymentIntent(
            payee="0xAAA", amount="1.00", service="svc", reason="r", chain="BASE-SEPOLIA",
        ))
        d2 = PaymentExecutor.compute_intent_digest(exec1, PaymentIntent(
            payee="0xBBB", amount="1.00", service="svc", reason="r", chain="BASE-SEPOLIA",
        ))
        assert d1 != d2

    def test_case_insensitive_payee(self):
        exec1 = PaymentExecutor.__new__(PaymentExecutor)
        d1 = PaymentExecutor.compute_intent_digest(exec1, PaymentIntent(
            payee="0xAbC", amount="1.00", service="svc", reason="r", chain="BASE-SEPOLIA",
        ))
        d2 = PaymentExecutor.compute_intent_digest(exec1, PaymentIntent(
            payee="0xabc", amount="1.00", service="svc", reason="r", chain="BASE-SEPOLIA",
        ))
        assert d1 == d2


# ── 3. Replay / nonce+JTI blocking ───────────────────────────────────

class TestReplayProtection:
    def test_jti_uniqueness(self, private_key):
        """Each token has a unique JTI."""
        jtis = set()
        for _ in range(10):
            _, jti = issue_token(
                private_key=private_key,
                agent_id="agent-1", action="pay", resource="0xabc",
                action_digest="sha256:test", decision="approve",
                receipt_hash="sha256:test", tenant="test",
            )
            assert jti not in jtis
            jtis.add(jti)

    def test_token_expired_rejected(self, private_key):
        """Expired tokens are rejected."""
        token, _ = issue_token(
            private_key=private_key,
            agent_id="agent-1", action="pay", resource="0xabc",
            action_digest="sha256:test", decision="approve",
            receipt_hash="sha256:test", tenant="test",
            ttl_seconds=-10,  # Already expired
        )
        import jwt
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_token(token, private_key.public_key(), leeway=0)

    def test_valid_token_verified(self, private_key):
        """Valid tokens pass verification."""
        token, jti = issue_token(
            private_key=private_key,
            agent_id="agent-1", action="pay", resource="0xabc",
            action_digest="sha256:test", decision="approve",
            receipt_hash="sha256:test", tenant="test",
        )
        payload = verify_token(token, private_key.public_key())
        assert payload["jti"] == jti
        assert payload["sub"] == "agent-1"


# ── 4. Deny path produces signed denial receipt ──────────────────────

class TestDenyPath:
    def test_denial_receipt_signed(self, receipt_chain):
        receipt = receipt_chain.sign_decision(
            request_digest="sha256:test",
            policy_version="sha256:policy",
            decision="deny",
            reasons=["RESOURCE_OUT_OF_SCOPE:scope"],
        )
        assert receipt.decision == "deny"
        assert receipt.signature != ""
        assert receipt.receipt_hash.startswith("sha256:")
        assert receipt.token_jti is None  # No token for denials

    def test_denial_in_chain(self, receipt_chain):
        """Denial receipts are properly chain-linked."""
        r1 = receipt_chain.sign_decision(
            request_digest="sha256:good", policy_version="sha256:p",
            decision="approve", reasons=[], token_jti="jti-1",
        )
        r2 = receipt_chain.sign_decision(
            request_digest="sha256:bad", policy_version="sha256:p",
            decision="deny", reasons=["DENIED"],
        )
        assert r2.prev_receipt == r1.receipt_hash
        assert r2.seq == "2"


# ── 5. Per-tenant key isolation ───────────────────────────────────────

class TestPerTenantKeys:
    def test_different_tenants_different_keys(self):
        """Each tenant gets a distinct signing key."""
        exec_a = PaymentExecutor(
            source_wallet="0x000", tenant="tenant-a", allowed_payees=["0xaaa"],
        )
        exec_b = PaymentExecutor(
            source_wallet="0x000", tenant="tenant-b", allowed_payees=["0xbbb"],
        )
        assert exec_a._kid != exec_b._kid
        jwk_a = exec_a.get_public_key_jwk()
        jwk_b = exec_b.get_public_key_jwk()
        assert jwk_a["x"] != jwk_b["x"]
        assert jwk_a["kid"] != jwk_b["kid"]

    def test_cross_tenant_verification_fails(self):
        """Receipts signed by tenant-a cannot be verified with tenant-b's key."""
        exec_a = PaymentExecutor(
            source_wallet="0x000", tenant="tenant-a", allowed_payees=["0xaaa"],
        )
        exec_b = PaymentExecutor(
            source_wallet="0x000", tenant="tenant-b", allowed_payees=["0xbbb"],
        )

        # Sign a receipt with tenant-a's key
        exec_a._receipt_chain.sign_decision(
            request_digest="sha256:test", policy_version="sha256:p",
            decision="approve", reasons=[], token_jti="jti-1",
        )
        chain_a = exec_a.get_receipt_chain()

        # Verify with tenant-b's key — should fail
        result = verify_chain(chain_a, exec_b.get_public_key_jwk())
        assert result.receipt_integrity == "FAIL"


# ── 6. Isolator severity classification ───────────────────────────────

class TestIsolator:
    def test_critical_on_injection_keywords(self):
        assert classify_severity(["injection detected"]) == "CRITICAL"
        assert classify_severity(["attacker redirect"]) == "CRITICAL"
        assert classify_severity(["bypass authorization"]) == "CRITICAL"

    def test_high_on_multiple_violations(self):
        assert classify_severity([
            "RESOURCE_OUT_OF_SCOPE:scope",
            "AMOUNT_EXCEEDS_CAP:50>1",
        ]) == "HIGH"

    def test_medium_on_single_violation(self):
        assert classify_severity(["RESOURCE_OUT_OF_SCOPE:scope"]) == "MEDIUM"

    def test_high_on_extreme_amount(self):
        assert classify_severity(["AMOUNT_EXCEEDS_CAP:100>1"]) == "HIGH"

    def test_isolation_record_signed(self):
        key = Ed25519PrivateKey.generate()
        isolator = Isolator(
            tenant="test", private_key=key, kid="iso-kid",
            wallet_address="0xwallet", chain="BASE-SEPOLIA",
        )
        record = isolator.evaluate_and_contain(
            agent_id="rogue-agent",
            denial_reasons=["RESOURCE_OUT_OF_SCOPE:scope", "AMOUNT_EXCEEDS_CAP:50>1"],
            denial_receipt_hash="sha256:denial",
        )
        assert record is not None
        assert record.severity == "HIGH"
        assert record.signature != ""
        assert record.receipt_hash.startswith("sha256:")
        assert isolator.is_agent_revoked("rogue-agent")

    def test_no_isolation_below_threshold(self):
        key = Ed25519PrivateKey.generate()
        isolator = Isolator(
            tenant="test", private_key=key, kid="iso-kid",
        )
        record = isolator.evaluate_and_contain(
            agent_id="normal-agent",
            denial_reasons=["RESOURCE_OUT_OF_SCOPE:scope"],
            denial_receipt_hash="sha256:denial",
        )
        assert record is None
        assert not isolator.is_agent_revoked("normal-agent")


# ── 7. Receipt chain integrity ────────────────────────────────────────

class TestReceiptChain:
    def test_chain_verified(self, private_key, receipt_chain):
        for i in range(5):
            receipt_chain.sign_decision(
                request_digest=f"sha256:req{i}",
                policy_version="sha256:p",
                decision="approve" if i % 2 == 0 else "deny",
                reasons=[] if i % 2 == 0 else [f"reason-{i}"],
                token_jti=f"jti-{i}" if i % 2 == 0 else None,
            )

        envelopes = [r.envelope_dict() for r in receipt_chain.get_receipts()]
        import base64
        pub_bytes = private_key.public_key().public_bytes_raw()
        x_b64url = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode("ascii")
        jwk = {"kty": "OKP", "crv": "Ed25519", "kid": "test-kid-001", "x": x_b64url}

        result = verify_chain(envelopes, jwk)
        assert result.receipt_integrity == "PASS"
        assert result.chain_validity == "PASS"

    def test_tampered_receipt_fails(self, private_key, receipt_chain):
        receipt_chain.sign_decision(
            request_digest="sha256:req", policy_version="sha256:p",
            decision="approve", reasons=[], token_jti="jti-1",
        )
        envelopes = [r.envelope_dict() for r in receipt_chain.get_receipts()]

        # Tamper with the receipt body
        envelopes[0]["body"]["decision"] = "deny"

        import base64
        pub_bytes = private_key.public_key().public_bytes_raw()
        x_b64url = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode("ascii")
        jwk = {"kty": "OKP", "crv": "Ed25519", "kid": "test-kid-001", "x": x_b64url}

        result = verify_chain(envelopes, jwk)
        assert result.receipt_integrity == "FAIL"


# ── 8. Merkle inclusion proofs ────────────────────────────────────────

class TestMerkle:
    def test_root_deterministic(self):
        hashes = ["aa" * 32, "bb" * 32]
        root1 = compute_unified_root(hashes)
        root2 = compute_unified_root(hashes)
        assert root1 == root2
        assert root1.startswith("sha256:")

    def test_inclusion_proof_valid(self):
        hashes = ["aa" * 32, "bb" * 32, "cc" * 32]
        root = compute_unified_root(hashes)
        proof = compute_inclusion_proof(hashes, "bb" * 32)
        assert proof is not None
        assert proof["root"] == root
        assert proof["leaf_index"] == 1

    def test_missing_hash_no_proof(self):
        hashes = ["aa" * 32, "bb" * 32]
        proof = compute_inclusion_proof(hashes, "ff" * 32)
        assert proof is None
