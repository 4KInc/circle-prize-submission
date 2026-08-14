"""On-chain spending policies for Circle Agent Wallets.

Defines and documents the spending policies that should be enforced
at the Circle wallet layer (independent of Verigate's application-layer
screening). This provides defense-in-depth: even if Verigate is bypassed,
Circle's on-chain policies independently constrain the wallet.

Policy deployment:
  - Policies are defined here and can be deployed via Circle CLI
  - The treasury wallet can only pay validators (destination whitelist)
  - Per-transaction and daily limits are enforced on-chain
  - Rate limits prevent evidence purchase spam

These policies are INDEPENDENT from Verigate's risk scoring.
Circle enforces them at the wallet layer. Verigate documents them
in the proof bundle for auditors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("circle.on_chain_policy")


@dataclass
class SpendingPolicy:
    """A Circle-compatible wallet spending policy."""
    name: str
    wallet: str
    rules: list[dict] = field(default_factory=list)
    deployed: bool = False
    policy_id: str = ""

    def to_circle_format(self) -> dict:
        """Format for Circle CLI deployment."""
        return {
            "name": self.name,
            "wallet": self.wallet,
            "rules": self.rules,
            "status": "deployed" if self.deployed else "pending",
            "policy_id": self.policy_id,
        }


# ── Treasury Wallet Policy ──────────────────────────────────────────
# The treasury can only pay validators, with strict limits.

TREASURY_POLICY = SpendingPolicy(
    name="verigate-treasury-step-up",
    wallet="0x0c744ecb3949b3582cdd2dbc70dc876405eec44d",
    rules=[
        {
            "type": "transfer_limit",
            "description": "Max STEP_UP evidence fee per transaction",
            "max_amount": "5.00",
            "asset": "USDC",
            "rationale": "Dynamic pricing caps at $5.00 for the largest transactions",
        },
        {
            "type": "daily_limit",
            "description": "Max daily evidence spend",
            "max_amount_per_day": "50.00",
            "asset": "USDC",
            "rationale": "At $0.02-$5.00 per STEP_UP, 50 max/day bounds daily exposure",
        },
        {
            "type": "destination_whitelist",
            "description": "Treasury can only pay authorized validators",
            "allowed_destinations": [
                "0xbe1424b7bcc149523f749ceb7a8316d8ba6ba558",  # Evidence Validator
            ],
            "rationale": "Treasury funds are ring-fenced for evidence purchases only",
        },
        {
            "type": "rate_limit",
            "description": "Max evidence purchases per hour",
            "max_transfers_per_hour": 20,
            "rationale": "Prevents evidence purchase spam from a compromised agent",
        },
    ],
)

# ── Customer Wallet Policy ──────────────────────────────────────────
# The customer wallet pays Verigate for screening.

CUSTOMER_POLICY = SpendingPolicy(
    name="verigate-customer-screening",
    wallet="0x5c34e3e05f0f1b9c4e3b92846791c6516dd431a2",
    rules=[
        {
            "type": "transfer_limit",
            "description": "Max screening fee per check",
            "max_amount": "0.10",
            "asset": "USDC",
            "rationale": "Screening fee is $0.05; 2x buffer for fee changes",
        },
        {
            "type": "daily_limit",
            "description": "Max daily screening spend",
            "max_amount_per_day": "25.00",
            "asset": "USDC",
            "rationale": "500 checks/day max at $0.05 each",
        },
        {
            "type": "destination_whitelist",
            "description": "Customer can only pay Verigate treasury",
            "allowed_destinations": [
                "0x0c744ecb3949b3582cdd2dbc70dc876405eec44d",  # Verigate Treasury
            ],
            "rationale": "Screening fees go to treasury only",
        },
    ],
)

# ── Validator Wallet Policy ─────────────────────────────────────────
# The validator wallet receives payments and has no outbound transfers.

VALIDATOR_POLICY = SpendingPolicy(
    name="verigate-validator-receive-only",
    wallet="0xbe1424b7bcc149523f749ceb7a8316d8ba6ba558",
    rules=[
        {
            "type": "transfer_limit",
            "description": "Validator does not initiate outbound transfers",
            "max_amount": "0.00",
            "asset": "USDC",
            "rationale": "Validator is receive-only; withdrawals require operator action",
        },
    ],
)


def get_all_policies() -> list[SpendingPolicy]:
    """Return all wallet spending policies."""
    return [TREASURY_POLICY, CUSTOMER_POLICY, VALIDATOR_POLICY]


def get_policy_for_wallet(wallet: str) -> SpendingPolicy | None:
    """Find the spending policy for a given wallet address."""
    wallet_lower = wallet.lower()
    for policy in get_all_policies():
        if policy.wallet.lower() == wallet_lower:
            return policy
    return None


def validate_transfer_against_policy(
    wallet: str, destination: str, amount: float,
) -> dict:
    """Check if a transfer would be allowed by the on-chain policy.

    This is an APPLICATION-SIDE check. The real enforcement happens
    at the Circle wallet layer independently.
    """
    policy = get_policy_for_wallet(wallet)
    if policy is None:
        return {"allowed": True, "reason": "no policy defined for this wallet"}

    violations = []
    for rule in policy.rules:
        if rule["type"] == "transfer_limit":
            max_amt = float(rule.get("max_amount", "999999"))
            if amount > max_amt:
                violations.append(f"Amount ${amount:.2f} exceeds limit ${max_amt:.2f}")

        if rule["type"] == "destination_whitelist":
            allowed = [d.lower() for d in rule.get("allowed_destinations", [])]
            if allowed and destination.lower() not in allowed:
                violations.append(f"Destination {destination[:12]}... not in whitelist")

    return {
        "allowed": len(violations) == 0,
        "policy": policy.name,
        "violations": violations,
    }
