"""Verigate Gate — the public SDK entry point.

    from verigate import Gate

    gate = Gate("circle://agent-wallet")
    receipt = gate.authorize(intent)
    gate.verify()
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

# Ensure engine + circle are importable
_ROOT = os.path.join(os.path.dirname(__file__), "..")
for subdir in ["engine", ""]:
    p = os.path.join(_ROOT, subdir) if subdir else _ROOT
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

from circle.executor import PaymentExecutor, PaymentIntent, PaymentResult, PaymentDenied
from circle.verifier import verify_payment_chain


@dataclass
class Intent:
    """A payment intent to be authorized through the gate."""
    payee: str
    amount: float
    service: str = ""
    reason: str = ""
    chain: str = "BASE-SEPOLIA"

    def to_payment_intent(self) -> PaymentIntent:
        return PaymentIntent(
            payee=self.payee,
            amount=str(self.amount),
            service=self.service,
            reason=self.reason,
            chain=self.chain,
        )


@dataclass
class VerifyResult:
    """Result of offline verification."""
    overall: str = "PENDING"
    signatures: str = "PENDING"
    hash_chain: str = "PENDING"
    merkle: str = "PENDING"
    receipt_count: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.overall == "PASS"


class Gate:
    """Verigate Gate — deterministic policy enforcement + signed receipts.

    Args:
        wallet: Circle wallet identifier. Use "circle://<wallet-id>" or a raw wallet address.
        policy: Path to a YAML policy file, or None for default policy.
        allowed_payees: List of allowed payee addresses.
        max_amount: Maximum per-transaction amount in USDC.
        tenant: Tenant identifier for receipt chain isolation.
    """

    def __init__(
        self,
        wallet: str,
        policy: str | None = None,
        allowed_payees: list[str] | None = None,
        max_amount: float = 1.0,
        tenant: str = "sdk",
        dry_run: bool = False,
    ):
        # Parse circle:// URI
        if wallet.startswith("circle://"):
            self._wallet = wallet[len("circle://"):]
        else:
            self._wallet = wallet

        self._tenant = tenant
        self._policy_path = policy

        # Load allowed payees from policy file if provided
        _payees = allowed_payees
        if policy and os.path.exists(policy) and not _payees:
            _payees = self._load_payees_from_policy(policy)

        self._executor = PaymentExecutor(
            source_wallet=self._wallet,
            tenant=tenant,
            allowed_payees=_payees,
            max_amount=max_amount,
            dry_run=dry_run,
        )

    @staticmethod
    def _load_payees_from_policy(path: str) -> list[str] | None:
        try:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f)
            return data.get("allowed_payees")
        except Exception:
            return None

    def authorize(self, intent: Intent | dict) -> dict:
        """Authorize a payment intent through the gate.

        Returns a signed receipt envelope (dict) on approval.
        Raises PaymentDenied on denial (which also contains a signed receipt).
        """
        if isinstance(intent, dict):
            intent = Intent(**intent)

        payment_intent = intent.to_payment_intent()
        result = self._executor.execute(payment_intent)
        return self._executor.get_receipt_chain()[-1]

    def authorize_or_deny(self, intent: Intent | dict) -> tuple[str, dict]:
        """Authorize and return (decision, receipt) without raising on denial."""
        if isinstance(intent, dict):
            intent = Intent(**intent)

        payment_intent = intent.to_payment_intent()
        try:
            result = self._executor.execute(payment_intent)
            return ("approve", self._executor.get_receipt_chain()[-1])
        except PaymentDenied:
            return ("deny", self._executor.get_receipt_chain()[-1])

    def verify(self) -> VerifyResult:
        """Verify the full receipt chain offline.

        Checks Ed25519 signatures, hash-chain continuity, and Merkle integrity.
        No network access needed.
        """
        envelopes = self._executor.get_receipt_chain()
        if not envelopes:
            return VerifyResult(overall="PASS", receipt_count=0)

        public_jwk = self._executor.get_public_key_jwk()
        merkle_root = self._executor.compute_merkle_root()

        report = verify_payment_chain(
            envelopes=envelopes,
            public_key_jwk=public_jwk,
            merkle_root=merkle_root,
        )

        return VerifyResult(
            overall=report.overall,
            signatures=report.signature_check,
            hash_chain=report.chain_check,
            merkle=report.merkle_check,
            receipt_count=report.receipt_count,
            errors=report.errors,
        )

    @property
    def receipts(self) -> list[dict]:
        """All receipt envelopes in the chain."""
        return self._executor.get_receipt_chain()

    @property
    def merkle_root(self) -> str | None:
        """Current Merkle root of the receipt chain."""
        try:
            return self._executor.compute_merkle_root()
        except ValueError:
            return None

    @property
    def public_key_jwk(self) -> dict:
        """Ed25519 public key in JWK format for third-party verification."""
        return self._executor.get_public_key_jwk()

    def export(self) -> dict:
        """Export the full proof bundle for offline verification."""
        return {
            "receipts": self.receipts,
            "merkle_root": self.merkle_root,
            "public_key_jwk": self.public_key_jwk,
            "tenant": self._tenant,
        }
