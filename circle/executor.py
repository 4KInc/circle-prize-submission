"""Receipt-producing payment executor.

Every payment decision — approve or deny — produces a signed,
independently verifiable receipt. This is NOT about enforcement
(Circle's Action Gate + MPC co-signer handles that). This is about
PROOF: cryptographic evidence of what was decided, why, and what settled.

WHY WE STILL EVALUATE POLICY:
Circle's Action Gate evaluates policy at the wallet layer. We evaluate
the SAME policy at the application layer — not to enforce (Circle does
that independently), but to PRODUCE A RECEIPT that documents the
decision. Without evaluating the policy ourselves, we couldn't sign a
receipt proving the decision was correct at the time it was made.

The receipt binds:
- WHO: x401 credential hash (agent identity)
- WHAT: policy_version hash (which rules were active)
- WHETHER: approve/deny decision with reasons
- WHERE: settlement tx hash (embedded AFTER on-chain settlement)

One receipt = one proof object. Independently verifiable with just
the public key (which is itself anchored on-chain via wallet signature).

Flow:
    1. Verify x401 credential (if provided)
    2. Evaluate intent against policy (to produce the receipt, not to enforce)
    3. If approved: execute transfer, sign receipt with tx hash
    4. If denied: sign denial receipt (equally valuable as proof)
    5. Circle's Action Gate independently enforces at the wallet layer
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

# Add engine to path
ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "engine")
if os.path.isdir(ENGINE_PATH) and ENGINE_PATH not in sys.path:
    sys.path.insert(0, ENGINE_PATH)

from gateway.canonical import canonicalize
from gateway.policy import Policy, PolicyEngine, PolicyRule
from gateway.receipts import Receipt, ReceiptChain
from gateway.tokens import issue_token
from gateway.merkle import compute_unified_root, compute_inclusion_proof
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from circle.cli import USDC_ADDRESSES, TransferResult, wallet_transfer

logger = logging.getLogger("circle.executor")


@dataclass
class PaymentIntent:
    """Structured payment intent from the ops agent."""
    payee: str
    amount: str
    service: str
    reason: str
    chain: str = "BASE-SEPOLIA"
    token_address: str | None = None
    x402_endpoint: str | None = None  # If set, use x402 protocol instead of direct transfer
    x401_credential: Any | None = None  # x401 credential binding agent identity

    def __post_init__(self):
        if self.token_address is None:
            self.token_address = USDC_ADDRESSES.get(self.chain, USDC_ADDRESSES["BASE-SEPOLIA"])


@dataclass
class PaymentResult:
    """Result of a gated payment execution."""
    decision: str
    receipt: dict
    receipt_hash: str
    intent_digest: str
    token_jti: str | None = None
    transfer: TransferResult | None = None
    denial_reasons: list[str] = field(default_factory=list)


class PaymentDenied(Exception):
    """Raised when the gate denies a payment."""
    def __init__(self, result: PaymentResult):
        self.result = result
        super().__init__(f"Payment denied: {result.denial_reasons}")


class PaymentExecutor:
    """Gated payment executor — deterministic policy eval + Circle CLI."""

    def __init__(
        self,
        source_wallet: str,
        tenant: str = "golden-path",
        allowed_payees: list[str] | None = None,
        max_amount: float = 1.0,
        private_key: Ed25519PrivateKey | None = None,
        kid: str | None = None,
        x401_verifier: Any | None = None,
    ):
        self.source_wallet = source_wallet
        self.tenant = tenant

        # Signing key (per-tenant)
        self._private_key = private_key or Ed25519PrivateKey.generate()
        self._kid = kid or f"gateway-{tenant}-{uuid.uuid4().hex[:8]}"

        # x401 credential verifier (optional — binds agent identity to receipts)
        self._x401_verifier = x401_verifier

        # Receipt chain
        self._receipt_chain = ReceiptChain(
            tenant=tenant,
            private_key=self._private_key,
            kid=self._kid,
        )

        # Payment policy
        self._allowed_payees = [p.lower() for p in (allowed_payees or [])]
        self._max_amount = max_amount
        self._policy = self._build_policy()
        self._engine = PolicyEngine(self._policy)

        # Track executed payments
        self.payments: list[PaymentResult] = []

    def _build_policy(self) -> Policy:
        return Policy(
            version="payment-v1",
            rules=[
                PolicyRule(
                    id="payment_actions",
                    type="allowlist",
                    config={"allowed_actions": ["pay", "transfer"]},
                ),
                PolicyRule(
                    id="payment_scope",
                    type="resource_scope",
                    config={"allowed_resources": self._allowed_payees},
                ),
                PolicyRule(
                    id="payment_rate",
                    type="rate_limit",
                    config={"max_actions": 5, "window_seconds": 60},
                ),
            ],
        )

    def compute_intent_digest(self, intent: PaymentIntent) -> str:
        obj = {
            "amount": intent.amount,
            "chain": intent.chain,
            "payee": intent.payee.lower(),
            "reason": intent.reason,
            "service": intent.service,
            "token": intent.token_address.lower(),
        }
        body_bytes = canonicalize(obj)
        return "sha256:" + hashlib.sha256(body_bytes).hexdigest()

    def execute(self, intent: PaymentIntent) -> PaymentResult:
        """Gate and execute a payment. Raises PaymentDenied if policy denies.

        Phase 2: receipt is signed AFTER settlement so the tx hash is
        embedded in the receipt body, creating a single proof object for
        decision → authorization → settlement.

        Phase 3: x401 credential verification — if a credential is
        provided, verify it before policy evaluation and bind the
        credential hash into the receipt.
        """
        intent_digest = self.compute_intent_digest(intent)

        # x401 credential verification (if provided)
        x401_hash = None
        if intent.x401_credential and self._x401_verifier:
            x401_result = self._x401_verifier.verify(intent.x401_credential)
            x401_hash = x401_result.credential_hash
            if not x401_result.valid:
                logger.warning(f"x401 credential verification failed: {x401_result.errors}")
                # Credential failure is a denial — produce signed receipt
                denial_receipt = self._receipt_chain.sign_decision(
                    request_digest=intent_digest,
                    policy_version=self._policy.policy_hash(),
                    decision="deny",
                    reasons=[f"X401_CREDENTIAL_INVALID:{','.join(x401_result.errors)}"],
                    delegation_context={"x401_credential_hash": x401_hash},
                )
                payment_result = PaymentResult(
                    decision="deny",
                    receipt=denial_receipt.envelope_dict(),
                    receipt_hash=denial_receipt.receipt_hash,
                    intent_digest=intent_digest,
                    denial_reasons=[f"X401_CREDENTIAL_INVALID:{','.join(x401_result.errors)}"],
                )
                self.payments.append(payment_result)
                raise PaymentDenied(payment_result)
            logger.info(f"x401 credential verified: issuer={x401_result.issuer} hash={x401_hash[:30]}...")
        elif intent.x401_credential:
            # Credential provided but no verifier configured — hash it anyway for binding
            x401_hash = intent.x401_credential.credential_hash()
            logger.info(f"x401 credential hash bound (no verifier): {x401_hash[:30]}...")

        # Amount cap check (separate from policy engine for clarity)
        amount_float = float(intent.amount)
        amount_denied = amount_float > self._max_amount

        # Policy evaluation (deterministic, zero-LLM)
        result = self._engine.evaluate(
            agent_id="ops-agent",
            action="pay",
            resource=intent.payee.lower(),
            parameters={"amount": intent.amount},
        )

        if amount_denied:
            result.decision = "deny"
            result.reason_codes.append(f"AMOUNT_EXCEEDS_CAP:{intent.amount}>{self._max_amount}")

        if result.decision == "deny":
            deny_delegation = {"x401_credential_hash": x401_hash} if x401_hash else None
            denial_receipt = self._receipt_chain.sign_decision(
                request_digest=intent_digest,
                policy_version=self._policy.policy_hash(),
                decision="deny",
                reasons=result.reason_codes,
                delegation_context=deny_delegation,
            )
            payment_result = PaymentResult(
                decision="deny",
                receipt=denial_receipt.envelope_dict(),
                receipt_hash=denial_receipt.receipt_hash,
                intent_digest=intent_digest,
                denial_reasons=result.reason_codes,
            )
            self.payments.append(payment_result)
            raise PaymentDenied(payment_result)

        # Approved — issue token, execute, THEN sign receipt with tx hash
        token_jti = str(uuid.uuid4())

        # Issue scoped authorization token (before transfer, for idempotency)
        token, _ = issue_token(
            private_key=self._private_key,
            agent_id="ops-agent",
            action="pay",
            resource=intent.payee.lower(),
            action_digest=intent_digest,
            decision="approve",
            receipt_hash="pending",  # receipt not yet signed
            tenant=self.tenant,
            receipt_jti=token_jti,
        )
        logger.info(f"Token issued: jti={token_jti[:12]}... ttl=60s")

        # Execute payment via Circle CLI
        x402_response = None
        if intent.x402_endpoint:
            # x402 protocol: circle services pay handles 402 → sign → settle
            from circle.cli import services_pay
            logger.info(f"x402 payment: {intent.x402_endpoint}")
            try:
                x402_response = services_pay(
                    url=intent.x402_endpoint,
                    address=self.source_wallet,
                    chain=intent.chain,
                    max_amount=intent.amount,
                )
                logger.info(f"x402 payment confirmed — service data received")
            except Exception as e:
                logger.warning(f"x402 payment failed ({e}), falling back to direct transfer")

        # Direct transfer for on-chain settlement proof (JTI = idempotency key)
        transfer = wallet_transfer(
            source=self.source_wallet,
            destination=intent.payee,
            amount=intent.amount,
            chain=intent.chain,
            token_address=intent.token_address,
            idempotency_key=token_jti,
        )
        logger.info(f"Transfer confirmed: tx={transfer.tx_hash[:16]}...")

        # NOW sign receipt with settlement tx hash embedded
        delegation = {
            "settlement_tx": transfer.tx_hash,
            "settlement_chain": intent.chain,
            "settlement_block": transfer.block_height,
            "settlement_payee": transfer.destination,
            "settlement_amount": transfer.amount,
        }
        # Bind x401 credential hash into the receipt (identity + decision + settlement)
        if x401_hash:
            delegation["x401_credential_hash"] = x401_hash

        receipt = self._receipt_chain.sign_decision(
            request_digest=intent_digest,
            policy_version=self._policy.policy_hash(),
            decision="approve",
            reasons=[],
            token_jti=token_jti,
            delegation_context=delegation,
        )

        payment_result = PaymentResult(
            decision="approve",
            receipt=receipt.envelope_dict(),
            receipt_hash=receipt.receipt_hash,
            intent_digest=intent_digest,
            token_jti=token_jti,
            transfer=transfer,
        )
        self.payments.append(payment_result)
        return payment_result

    def get_receipt_chain(self) -> list[dict]:
        return [r.envelope_dict() for r in self._receipt_chain.get_receipts()]

    def get_receipt_hashes(self) -> list[str]:
        """Return receipt hashes (hex, no prefix) for Merkle tree."""
        return self._receipt_chain.get_receipt_hashes()

    def compute_merkle_root(self) -> str:
        """Compute Merkle batch root over all receipts.

        SCALE NOTE: In production, receipts are batched into epochs
        (e.g., every 1000 receipts or every hour). Each epoch produces
        a Merkle root that is anchored on-chain. Verification of a
        single receipt requires only the receipts in its epoch, not the
        full history. This makes verification O(log n) within an epoch
        rather than O(n) across the full chain.
        """
        hashes = self.get_receipt_hashes()
        if not hashes:
            raise ValueError("No receipts to compute Merkle root")
        return compute_unified_root(hashes)

    def compute_inclusion_proof(self, receipt_hash: str) -> dict | None:
        """Compute Merkle inclusion proof for a specific receipt."""
        target = receipt_hash.removeprefix("sha256:")
        hashes = self.get_receipt_hashes()
        return compute_inclusion_proof(hashes, target)

    def get_public_key_jwk(self) -> dict:
        import base64
        pub_bytes = self._private_key.public_key().public_bytes_raw()
        x_b64url = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode("ascii")
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "kid": self._kid,
            "use": "sig",
            "alg": "EdDSA",
            "x": x_b64url,
        }

    def anchor_public_key(self, wallet_address: str, chain: str) -> dict:
        """Anchor the public key on-chain via wallet signature.

        This solves the trust problem: "where does the verifier get the
        public key?" The wallet signs the JWK, creating a trust chain:
        public key → wallet signature → wallet is on-chain → verifiable.

        Without this, the verifier has to trust whoever gave them the
        export file. With this, they can verify the public key is endorsed
        by the on-chain wallet.
        """
        import json
        from circle.cli import wallet_sign_message

        jwk = self.get_public_key_jwk()
        jwk_canonical = json.dumps(jwk, sort_keys=True, separators=(",", ":"))
        jwk_hash = hashlib.sha256(jwk_canonical.encode()).hexdigest()

        try:
            sig_data = wallet_sign_message(
                address=wallet_address,
                chain=chain,
                message=jwk_hash,
            )
            return {
                "public_key_jwk": jwk,
                "jwk_hash": jwk_hash,
                "wallet_signature": sig_data.get("signature", ""),
                "wallet_address": wallet_address,
                "chain": chain,
                "anchored": True,
            }
        except Exception as e:
            logger.warning(f"Public key anchoring failed: {e}")
            return {
                "public_key_jwk": jwk,
                "jwk_hash": jwk_hash,
                "anchored": False,
                "error": str(e),
            }
