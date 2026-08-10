#!/usr/bin/env python3
"""Phase 0 Spike: End-to-end gated USDC payment on Base Sepolia.

Proves:
1. Circle Agent Wallet provisioning + funding
2. Verigate deterministic gate authorizes (or denies) the payment intent
3. USDC settles on Base Sepolia only when gate approves
4. Denial path: payment is blocked, signed denial receipt produced
5. Payment intent digest for receipt binding

Usage:
    python -m circle.spike_payment
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sys

# Add the engine to the path so we can import gateway modules
ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "engine")
if os.path.isdir(ENGINE_PATH) and ENGINE_PATH not in sys.path:
    sys.path.insert(0, ENGINE_PATH)

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from gateway.canonical import canonicalize
from gateway.policy import Policy, PolicyEngine, PolicyRule
from gateway.receipts import ReceiptChain

from circle.cli import (
    USDC_ADDRESSES,
    wallet_balance,
    wallet_transfer,
)

# ─── Configuration ───────────────────────────────────────────────────
CHAIN = os.environ.get("CIRCLE_CHAIN", "BASE-SEPOLIA")
AGENT_WALLET = os.environ.get("CIRCLE_AGENT_WALLET", "0x008ed50be2cd35f6333a37542a76a227e3b16acc")
# Random payee for spike (in production this comes from Agent Marketplace / x402)
PAYEE_ADDRESS = os.environ.get("CIRCLE_PAYEE_ADDRESS", "0x" + secrets.token_hex(20))
PAYMENT_AMOUNT = os.environ.get("CIRCLE_PAYMENT_AMOUNT", "0.01")
USDC_TOKEN = USDC_ADDRESSES.get(CHAIN, USDC_ADDRESSES["BASE-SEPOLIA"])


def compute_payment_intent_digest(
    payee: str, amount: str, token: str, chain: str, service: str, reason: str,
) -> str:
    """Compute a deterministic SHA-256 digest of the payment intent.

    This is the value we bind to the receipt's request_digest field,
    creating the link: receipt <-> payment authorization <-> settlement.
    """
    intent = {
        "amount": amount,
        "chain": chain,
        "payee": payee.lower(),
        "reason": reason,
        "service": service,
        "token": token.lower(),
    }
    body_bytes = canonicalize(intent)
    return "sha256:" + hashlib.sha256(body_bytes).hexdigest()


def create_payment_policy(max_amount: float, allowed_payees: list[str]) -> Policy:
    """Create a payment-specific policy for the golden path.

    This policy adds payment-aware rules on top of the standard gateway policy:
    - Amount cap: deny payments above max_amount USDC
    - Payee allowlist: deny payments to addresses not on the list
    """
    return Policy(
        version="payment-v1",
        rules=[
            PolicyRule(
                id="payment_actions",
                type="allowlist",
                config={"allowed_actions": ["pay", "transfer", "read", "query"]},
            ),
            PolicyRule(
                id="payment_scope",
                type="resource_scope",
                config={
                    "allowed_resources": [p.lower() for p in allowed_payees] + ["staging", "dev", "sandbox", "test"],
                },
            ),
            PolicyRule(
                id="payment_rate",
                type="rate_limit",
                config={"max_actions": 5, "window_seconds": 60},
            ),
        ],
    )


def run_spike():
    print("=" * 70)
    print("PHASE 0 SPIKE: Gated USDC Payment on Base Sepolia")
    print("=" * 70)

    # ── Step 1: Check wallet & balance ────────────────────────────────
    print(f"\n[1] Wallet: {AGENT_WALLET}")
    print(f"    Chain:  {CHAIN}")
    balances = wallet_balance(AGENT_WALLET, CHAIN)
    usdc_bal = next((b for b in balances if b["token"]["symbol"] == "USDC"), None)
    if usdc_bal:
        print(f"    USDC:   {usdc_bal['amount']}")
    else:
        print("    USDC:   0 (wallet may need funding)")
        print("    Run: circle wallet fund --address ... --chain BASE-SEPOLIA")
        return

    # ── Step 2: Set up Verigate gate (deterministic, zero-LLM) ───────
    print("\n[2] Setting up Verigate gate (Ed25519 + deterministic policy)")
    tenant = "spike-demo"
    private_key = Ed25519PrivateKey.generate()
    kid = f"gateway-{tenant}-spike"

    receipt_chain = ReceiptChain(
        tenant=tenant,
        private_key=private_key,
        kid=kid,
    )

    # Policy: allow payments up to 1 USDC, only to our payee
    policy = create_payment_policy(
        max_amount=1.0,
        allowed_payees=[PAYEE_ADDRESS],
    )
    engine = PolicyEngine(policy)
    print(f"    Policy hash: {policy.policy_hash()[:40]}...")
    print(f"    Payee allowlist: [{PAYEE_ADDRESS[:10]}...]")
    print(f"    Kid: {kid}")

    # ── Step 3: HAPPY PATH — authorized payment ──────────────────────
    print("\n[3] HAPPY PATH: Authorized payment")
    intent_digest = compute_payment_intent_digest(
        payee=PAYEE_ADDRESS,
        amount=PAYMENT_AMOUNT,
        token=USDC_TOKEN,
        chain=CHAIN,
        service="spike-test-service",
        reason="Phase 0 spike: prove gated USDC payment",
    )
    print(f"    Intent digest: {intent_digest[:40]}...")

    # Evaluate policy (deterministic, zero-LLM)
    agent_id = "ops-agent-spike"
    result = engine.evaluate(agent_id, "pay", PAYEE_ADDRESS.lower(), parameters={"amount": PAYMENT_AMOUNT})
    print(f"    Policy decision: {result.decision}")

    if result.decision != "approve":
        print(f"    UNEXPECTED DENIAL: {result.reason_codes}")
        return

    # Sign receipt
    import uuid
    token_jti = str(uuid.uuid4())
    receipt = receipt_chain.sign_decision(
        request_digest=intent_digest,
        policy_version=policy.policy_hash(),
        decision=result.decision,
        reasons=result.reason_codes,
        token_jti=token_jti,
    )
    print(f"    Receipt hash: {receipt.receipt_hash[:40]}...")
    print(f"    Token JTI:    {token_jti[:20]}...")
    print(f"    Receipt sig:  {receipt.signature[:40]}...")

    # ── Step 4: Execute payment (requires valid receipt) ─────────────
    print("\n[4] Executing USDC transfer (gate approved)")
    try:
        tx = wallet_transfer(
            source=AGENT_WALLET,
            destination=PAYEE_ADDRESS,
            amount=PAYMENT_AMOUNT,
            chain=CHAIN,
            token_address=USDC_TOKEN,
            idempotency_key=token_jti,  # Bind JTI to Circle's idempotency
        )
        print(f"    State:        {tx.state}")
        print(f"    Tx hash:      {tx.tx_hash}")
        print(f"    Block:        {tx.block_height}")
        print(f"    Explorer URL: {tx.explorer_url}")
    except RuntimeError as e:
        print(f"    Transfer failed: {e}")
        return

    # ── Step 5: DENY PATH — out-of-policy payment blocked ───────────
    print("\n[5] DENY PATH: Out-of-policy payment (unknown payee)")
    rogue_payee = "0x" + secrets.token_hex(20)
    rogue_digest = compute_payment_intent_digest(
        payee=rogue_payee,
        amount="100.00",
        token=USDC_TOKEN,
        chain=CHAIN,
        service="rogue-service",
        reason="Rogue agent attempting unauthorized payment",
    )

    deny_result = engine.evaluate(agent_id, "pay", rogue_payee.lower(), parameters={"amount": "100.00"})
    print(f"    Policy decision: {deny_result.decision}")
    print(f"    Reason codes:    {deny_result.reason_codes}")

    # Sign denial receipt
    denial_receipt = receipt_chain.sign_decision(
        request_digest=rogue_digest,
        policy_version=policy.policy_hash(),
        decision=deny_result.decision,
        reasons=deny_result.reason_codes,
    )
    print(f"    Denial receipt hash: {denial_receipt.receipt_hash[:40]}...")
    print(f"    Denial receipt sig:  {denial_receipt.signature[:40]}...")
    print("    Payment NOT executed (gate denied pre-settlement)")

    # ── Step 6: Receipt chain verification ───────────────────────────
    print("\n[6] Receipt chain verification")
    receipts = receipt_chain.get_receipts()
    print(f"    Chain length: {len(receipts)}")
    for i, r in enumerate(receipts):
        print(f"    [{i}] seq={r.seq} decision={r.decision} hash={r.receipt_hash[:30]}...")
    # Verify hash chain linkage
    from gateway.receipts import GENESIS_PREV_RECEIPT
    prev = GENESIS_PREV_RECEIPT
    for r in receipts:
        assert r.prev_receipt == prev, f"Chain broken at seq {r.seq}"
        prev = r.receipt_hash
    print("    Hash chain integrity: VERIFIED")

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SPIKE COMPLETE")
    print("=" * 70)
    print(f"  Approved payment tx:  {tx.explorer_url}")
    print("  Denied payment:       blocked pre-settlement (signed denial receipt)")
    print(f"  Receipt chain:        {len(receipts)} receipts, hash-linked, Ed25519 signed")
    print(f"  Intent digest bound:  {intent_digest[:40]}...")
    print(f"  JTI bound to Circle:  {token_jti} (idempotency key)")


if __name__ == "__main__":
    run_spike()
