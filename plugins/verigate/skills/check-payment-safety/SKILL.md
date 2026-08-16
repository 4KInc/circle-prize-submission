---
name: check-payment-safety
description: "Before making any USDC payment from a Circle Agent Wallet, use Verigate to check if the payment is safe. Activate when the agent is about to execute a transfer, pay for a service, or spend USDC."
allowed-tools:
  - "mcp__verigate__check_payment"
  - "mcp__verigate__get_risk_score"
  - "mcp__verigate__check_payment_x402"
  - "mcp__verigate__get_gateway_status"
  - "mcp__verigate__get_receipt"
  - "mcp__verigate__get_evidence_bundle"
  - "Bash(circle services pay*)"
  - "Bash(circle wallet transfer*)"
---

# Check Payment Safety with Verigate

## Overview

Verigate is an autonomous payment security agent that checks USDC payments before they execute. It uses a three-state decision engine:

- **APPROVE** — Payment is safe. Proceed with the transfer.
- **STEP_UP** — Risk is uncertain. Verigate autonomously pays $0.02 to an Evidence Validator for independent verification, then makes a final decision.
- **DENY** — Payment is blocked. Do not proceed.

Every decision produces a signed, independently verifiable receipt.

## Prerequisites

- Circle Agent Wallet with USDC balance on Base Sepolia
- Verigate MCP server connected (see `.mcp.json`)
- Or: access to Verigate's x402 endpoint at `https://verigate.cloud/x402/security-check`

## Steps

### 1. Before Any USDC Payment

Before calling `circle wallet transfer` or paying for any x402 service, ALWAYS check the payment with Verigate first:

```
Use the check_payment tool with:
  payee: <destination wallet address>
  amount: <USDC amount>
  service: <what you're paying for>
  reason: <why you need to make this payment>
```

### 2. Handle the Decision

**If APPROVE:**
- The payment is safe
- Proceed with `circle wallet transfer` or `circle services pay`
- Save the receipt hash for your records

**If STEP_UP:**
- Verigate detected uncertainty (risk score 40-74 or confidence < 60%)
- Verigate will autonomously purchase evidence from a validator ($0.02 USDC)
- Wait for the final verdict before proceeding
- The receipt will contain the evidence purchase details

**If DENY:**
- The payment is BLOCKED
- DO NOT proceed with the transfer
- Check the denial reasons in the response
- Common reasons: payee not on allowlist, amount exceeds cap, injection pattern detected, velocity anomaly

### 3. Verify the Receipt

After any check, you can retrieve the signed receipt:

```
Use the get_receipt tool with:
  receipt_hash: <the hash from the check_payment response>
```

The receipt is cryptographically signed with Ed25519 and can be independently verified.

## Rules

1. **ALWAYS check before paying.** Never skip the security check, even for small amounts.
2. **NEVER proceed on DENY.** The payment was blocked for a reason.
3. **Wait on STEP_UP.** Let Verigate finish its evidence purchase before deciding.
4. **Save receipt hashes.** They are cryptographic proof of the security decision.
5. **The fee is $0.05 USDC** per check, settled via Circle Gateway nanopayments (gas-free).

## Payment Flow

```
Agent has task requiring USDC payment
    ↓
Call Verigate check_payment (costs $0.05 USDC)
    ↓
┌─────────────┬──────────────┬─────────────┐
│   APPROVE   │   STEP_UP    │    DENY     │
│ Score < 40  │ Score 40-74  │ Score > 75  │
│             │ or conf < 60%│             │
├─────────────┼──────────────┼─────────────┤
│ Proceed     │ Wait for     │ Do NOT      │
│ with payment│ evidence     │ proceed     │
│             │ ($0.02 spent)│             │
│             │ Then decide  │             │
└─────────────┴──────────────┴─────────────┘
    ↓                ↓               ↓
Signed receipt  Signed receipt  Signed receipt
(proof of       (proof of       (proof of
 approval)       investigation)  denial)
```

## Circle Agent Stack Integration

This skill works with the full Circle Agent Stack:

- **Agent Wallets** — Holds the USDC, enforces spending policies
- **Gateway Nanopayments** — Settles the $0.05 fee (gas-free, batched)
- **Circle CLI** — Executes transfers after approval
- **Agent Marketplace** — Verigate is discoverable as a security service

## Alternatives

- Without Verigate: Agent pays directly with no risk check (no safety net)
- With Circle's Action Gate only: Binary allow/block (no STEP_UP, no evidence purchase, no receipt)

## Disclaimer

Verigate provides risk assessment, not financial advice. The risk scorer uses heuristic analysis with Gemini RAG-grounded evidence reasoning. Always review denial reasons before escalating. Live on Base mainnet with real USDC.

## Additional Resources

- **Docs:** https://verigate.cloud/docs
- **Pricing:** https://verigate.cloud/pricing
- **OpenAPI Spec:** https://verigate.cloud/api/openapi-spec
- **GitHub:** https://github.com/4KInc/verigate
- **RAG Stats:** https://verigate.cloud/api/rag/stats
