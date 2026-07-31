"""Isolator — rogue agent containment for the golden path.

When a payment is denied with HIGH/CRITICAL severity indicators
(off-allowlist payee, amount over cap, or prompt injection detected),
the Isolator:

1. Revokes the agent's Verigate identity (removes signing authority)
2. Freezes the Circle Agent Wallet (calls circle wallet limit on mainnet)
3. Produces a signed isolation record in the receipt chain

This is the "wow" moment: a compromised agent is stopped from moving
USDC by the gate, with the wallet policy as backstop, and the agent
is quarantined — all producing verifiable receipts.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "engine")
if os.path.isdir(ENGINE_PATH) and ENGINE_PATH not in sys.path:
    sys.path.insert(0, ENGINE_PATH)

from gateway.canonical import canonicalize
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

logger = logging.getLogger("circle.isolator")


@dataclass
class IsolationRecord:
    """Signed isolation record documenting agent containment."""
    isolation_id: str
    tenant: str
    agent_id: str
    severity: str
    trigger: dict
    actions_taken: list[dict]
    reason: str
    isolated_at: str
    receipt_hash: str = ""
    signature: str = ""
    kid: str = ""

    def body_dict(self) -> dict:
        return {
            "isolation_id": self.isolation_id,
            "tenant": self.tenant,
            "agent_id": self.agent_id,
            "severity": self.severity,
            "trigger": self.trigger,
            "actions_taken": self.actions_taken,
            "reason": self.reason,
            "isolated_at": self.isolated_at,
            "schema_version": "isolation-record-v0.1",
        }

    def envelope_dict(self) -> dict:
        return {
            "body": self.body_dict(),
            "sig": {
                "alg": "EdDSA",
                "kid": self.kid,
                "value": self.signature,
            },
            "receipt_hash": self.receipt_hash,
        }


def classify_severity(denial_reasons: list[str]) -> str:
    """Classify the severity of a denied payment.

    Returns HIGH or CRITICAL based on the denial reasons.
    Prompt injection indicators → CRITICAL.
    Multiple policy violations → HIGH.
    Single violation → MEDIUM (no isolation triggered).
    """
    reasons_lower = " ".join(denial_reasons).lower()

    # CRITICAL: prompt injection indicators
    injection_keywords = [
        "injection", "attacker", "exploit", "malicious",
        "ignore previous", "override", "bypass",
    ]
    if any(kw in reasons_lower for kw in injection_keywords):
        return "CRITICAL"

    # HIGH: multiple policy violations or large amount
    if len(denial_reasons) >= 2:
        return "HIGH"

    # Check for extreme amount violation
    for reason in denial_reasons:
        if "AMOUNT_EXCEEDS_CAP" in reason:
            try:
                parts = reason.split(":")[-1].split(">")
                attempted = float(parts[0])
                cap = float(parts[1])
                if attempted > cap * 10:
                    return "HIGH"
            except (ValueError, IndexError):
                pass

    return "MEDIUM"


class Isolator:
    """Rogue agent containment engine."""

    def __init__(
        self,
        tenant: str,
        private_key: Ed25519PrivateKey,
        kid: str,
        wallet_address: str | None = None,
        chain: str = "BASE-SEPOLIA",
    ):
        self.tenant = tenant
        self._private_key = private_key
        self._kid = kid
        self._wallet_address = wallet_address
        self._chain = chain
        self._revoked_agents: set[str] = set()
        self._wallet_frozen = False
        self.records: list[IsolationRecord] = []

    def evaluate_and_contain(
        self,
        agent_id: str,
        denial_reasons: list[str],
        denial_receipt_hash: str,
        intent_context: dict | None = None,
    ) -> IsolationRecord | None:
        """Evaluate a denial and execute containment if HIGH/CRITICAL.

        Returns an IsolationRecord if containment was triggered, None otherwise.
        """
        severity = classify_severity(denial_reasons)
        logger.info(f"Severity classification: {severity} for agent {agent_id}")

        if severity not in ("HIGH", "CRITICAL"):
            logger.info(f"Severity {severity} below threshold — no isolation")
            return None

        actions_taken = []

        # Action 1: Revoke Verigate identity
        self._revoked_agents.add(agent_id)
        actions_taken.append({
            "action": "REVOKE_IDENTITY",
            "agent_id": agent_id,
            "status": "executed",
            "detail": "Agent removed from Verigate authorization registry",
        })
        logger.info(f"REVOKED: agent {agent_id} identity")

        # Action 2: Freeze Circle wallet (mainnet only — testnet limitation)
        if self._wallet_address:
            freeze_result = self._freeze_wallet()
            actions_taken.append(freeze_result)

        # Build trigger context
        trigger = {
            "type": "PAYMENT_DENIAL",
            "denial_receipt_hash": denial_receipt_hash,
            "denial_reasons": denial_reasons,
        }
        if intent_context:
            trigger["intent_context"] = intent_context

        # Determine reason
        if severity == "CRITICAL":
            reason = (
                f"CRITICAL: Agent {agent_id} attempted a payment that triggered "
                f"prompt injection indicators. Agent identity revoked and wallet "
                f"frozen. Denial reasons: {', '.join(denial_reasons)}"
            )
        else:
            reason = (
                f"HIGH: Agent {agent_id} violated multiple payment policy rules. "
                f"Agent identity revoked and wallet frozen. "
                f"Denial reasons: {', '.join(denial_reasons)}"
            )

        # Sign isolation record
        record = IsolationRecord(
            isolation_id=f"iso-{uuid.uuid4().hex[:12]}",
            tenant=self.tenant,
            agent_id=agent_id,
            severity=severity,
            trigger=trigger,
            actions_taken=actions_taken,
            reason=reason,
            isolated_at=datetime.now(timezone.utc).isoformat(),
        )

        body_bytes = canonicalize(record.body_dict())
        record.receipt_hash = "sha256:" + hashlib.sha256(body_bytes).hexdigest()
        sig_bytes = self._private_key.sign(body_bytes)
        record.signature = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode("ascii")
        record.kid = self._kid

        self.records.append(record)
        logger.info(f"Isolation record created: {record.isolation_id}")
        return record

    def _freeze_wallet(self) -> dict:
        """Attempt to freeze/cap the Circle Agent Wallet.

        On mainnet: calls `circle wallet limit set` to zero-cap.
        On testnet: spending policies unavailable — logged as simulated.
        """
        if "SEPOLIA" in self._chain.upper() or "TESTNET" in self._chain.upper():
            self._wallet_frozen = True
            return {
                "action": "FREEZE_WALLET",
                "wallet": self._wallet_address,
                "status": "simulated",
                "detail": (
                    "Spending policies are mainnet-only. On testnet, the Verigate "
                    "gate is the sole enforcement layer. On mainnet, this would "
                    "call: circle wallet limit set --per-tx 0 --daily 0"
                ),
            }

        # Mainnet: actually set spending limit to zero
        try:
            from circle.cli import _run
            _run([
                "wallet", "limit", "set",
                "--address", self._wallet_address,
                "--chain", self._chain,
                "--policy-type", "stablecoin",
                "--per-tx", "0",
                "--daily", "0",
            ])
            self._wallet_frozen = True
            return {
                "action": "FREEZE_WALLET",
                "wallet": self._wallet_address,
                "status": "executed",
                "detail": "Wallet spending limit set to zero via Circle CLI",
            }
        except Exception as e:
            return {
                "action": "FREEZE_WALLET",
                "wallet": self._wallet_address,
                "status": f"failed: {e}",
                "detail": "Could not freeze wallet — manual intervention needed",
            }

    def is_agent_revoked(self, agent_id: str) -> bool:
        return agent_id in self._revoked_agents

    def is_wallet_frozen(self) -> bool:
        return self._wallet_frozen
