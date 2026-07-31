# SPIKE.md — Phase 0 Spike Results

**Date:** 2026-07-31
**Status:** COMPLETE — all four questions answered, payment confirmed on Base Sepolia.

---

## Question 1: End-to-end payment works

**YES.** Proven with two real transactions on Base Sepolia:

### Manual test (CLI direct)
- **Tx:** `0xc01cd174f8b6f6de681fe6e6b1c070a8ad416e76600b3535a811be7391eed408`
- **Explorer:** https://sepolia.basescan.org/tx/0xc01cd174f8b6f6de681fe6e6b1c070a8ad416e76600b3535a811be7391eed408
- 0.01 USDC, agent wallet → random address, confirmed block 44853274

### Gated spike (Python → CLI → Verigate gate → settlement)
- **Tx:** `0xf0823e2b98845fa43e03b889ec5c6aafe2ffc85fac1bfa6d3cfc2c16036b1896`
- **Explorer:** https://sepolia.basescan.org/tx/0xf0823e2b98845fa43e03b889ec5c6aafe2ffc85fac1bfa6d3cfc2c16036b1896
- 0.01 USDC, gate-approved, JTI bound to Circle's idempotency key, confirmed block 44853816

### What was proven:
1. **Wallet provisioning:** Circle Agent Wallet exists at `0x008ed50be2cd35f6333a37542a76a227e3b16acc` on Base Sepolia
2. **Funding:** Faucet drip provided 20 USDC (testnet)
3. **Transfer:** `circle wallet transfer` with `--token` (USDC contract) settles in ~7 seconds
4. **Gateway deposit:** Nanopayment gateway deposit also works (`circle gateway deposit --method direct`)
5. **Denial path:** Out-of-policy payment produces a signed denial receipt and NO transfer is attempted

---

## Question 2: The enforcement hook

**Executor-mediated enforcement + Circle wallet-layer policy as belt-and-suspenders.**

### Chosen model: EXECUTOR-MEDIATED

Circle provides **no external authorization callback or webhook** for pre-settlement approval. The x402/transfer flow is fire-and-settle — once `circle wallet transfer` or `circle services pay` is invoked, the CLI signs and submits.

Therefore:

1. **Primary enforcement (Verigate gate):** The payment executor calls `POST /authorize` with the structured payment intent `{payee, amount, token, chain, service, reason}`. The deterministic policy engine evaluates:
   - Payee allowlist check
   - Amount cap check
   - Rate limit check
   - Action allowlist check

   If **approved**: issues a 60s single-use Ed25519 token + signed receipt. The token's JTI becomes the Circle transfer's idempotency key.

   If **denied**: signed denial receipt, no token, no CLI invocation. Payment is blocked **pre-settlement**.

2. **Secondary enforcement (Circle wallet-layer policy):** On mainnet, the Circle Agent Wallet enforces spending policies (per-tx cap, daily/weekly/monthly caps, recipient allowlist/blocklist) at the wallet layer before the tx is submitted to the chain. This is the independent second wall.

   **Testnet limitation:** Spending policies are **mainnet only** (`circle wallet limit` returns error on testnet). On Base Sepolia we can only demonstrate the Verigate gate as the enforcement layer. The Circle policy wall is demonstrated during the mainnet dry-run (Phase 5).

3. **Isolation (rogue containment):** The Isolator agent can revoke the agent's Verigate identity AND, on mainnet, call `circle wallet limit set` to freeze or zero-cap the wallet. Both produce signed isolation records.

### Why this is secure:
- The executor is a deterministic Python process, not an LLM — no prompt injection can bypass policy eval
- The token JTI is single-use and 60s TTL — replay is impossible
- The JTI is also the Circle idempotency key — even if someone captures the CLI command, Circle rejects the duplicate
- On mainnet, Circle's wallet policy provides an independent second wall that the agent cannot modify

---

## Question 3: SDK boundary

**Python CLI shell-out via `circle/cli.py`.**

### Decision: Shell out to Circle CLI from Python

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **CLI shell-out** | Same stack, no new runtime, CLI handles all crypto (EIP-3009, wallet key mgmt), proven working | Subprocess overhead (~2s), output parsing | **CHOSEN** |
| TS microservice | Native x402 batching lib, clean API | New runtime (Node/Bun), deployment complexity, cross-service auth | Rejected |
| Python REST | No subprocess | No official Python SDK for Agent Wallets/x402, would need to reverse-engineer auth | Rejected |
| Python wallet SDK | PyPI packages exist | Only cover developer-controlled wallets, not Agent Stack features | Rejected |

### Implementation: `circle/cli.py`

Thin wrapper exposing:
- `wallet_list(chain)` → list wallets
- `wallet_balance(address, chain)` → token balances
- `wallet_fund(address, chain, amount)` → faucet drip (testnet)
- `wallet_transfer(source, dest, amount, chain, token, idempotency_key)` → execute transfer, return `TransferResult` with tx hash + explorer URL
- `USDC_ADDRESSES` dict for token contract addresses per chain

All functions call the `circle` CLI binary with `-o json` and parse the output. The binary path is configurable via `CIRCLE_CLI_PATH` env var.

---

## Question 4: EIP-3009 digest — receipt-to-payment binding

### The binding problem

The Circle CLI **abstracts EIP-3009 signing internally**. When we call `circle wallet transfer`, the CLI:
1. Constructs the EIP-3009 `TransferWithAuthorization` typed data
2. Signs it with the wallet's MPC key share
3. Submits the signed authorization to the chain
4. Returns the tx hash

We **never see** the raw EIP-3009 digest bytes. This is by design — the wallet's private key shares are never exposed.

### Our binding approach: Payment Intent Digest

Instead of binding to the EIP-3009 digest (which we can't access), we bind to a **deterministic payment intent digest** that captures the same semantic content:

```python
def compute_payment_intent_digest(payee, amount, token, chain, service, reason):
    intent = {
        "amount": amount,
        "chain": chain,
        "payee": payee.lower(),
        "reason": reason,
        "service": service,
        "token": token.lower(),
    }
    body_bytes = canonicalize(intent)  # RFC 8785 JCS
    return "sha256:" + hashlib.sha256(body_bytes).hexdigest()
```

### Three-way binding chain

```
Receipt.request_digest ← payment_intent_digest (pre-settlement)
Receipt.token_jti      ← Circle idempotency_key (1:1 binding)
Receipt.settlement_tx  ← tx_hash from Circle (post-settlement, added in Phase 2)
```

This creates an unforgeable chain: **decision → authorization → settlement**.

- The `request_digest` proves what was authorized (payee, amount, service, reason)
- The `token_jti` = Circle's `idempotency_key` proves the authorization was consumed exactly once
- The `settlement_tx` (Phase 2) proves the on-chain settlement matches the authorization

### Verifier cross-reference (Phase 2)

The offline verifier will:
1. Validate the receipt's Ed25519 signature
2. Verify hash chain continuity
3. Verify Merkle inclusion proof
4. Fetch the on-chain tx via Basescan API
5. Confirm: tx destination == receipt's payee, tx amount == receipt's amount
6. Confirm: anchor tx root covers this receipt's Merkle leaf

### Deviation from prompt

The prompt asked for "the exact bytes/struct we will hash to bind a receipt to a payment authorization." Since the CLI abstracts EIP-3009 signing, we cannot access the typed data hash. Our payment intent digest is **semantically equivalent** — it captures the same authorization parameters (payee, amount, token, chain) and is deterministic via RFC 8785 canonicalization. The JTI-to-idempotency binding ensures 1:1 correlation.

---

## Spike artifacts

| File | Purpose |
|------|---------|
| `circle/cli.py` | Circle CLI Python wrapper |
| `circle/spike_payment.py` | Spike script (run with `python -m circle.spike_payment`) |
| `SPIKE.md` | This document |

## Wallet info

| Field | Value |
|-------|-------|
| Agent wallet | `0x008ed50be2cd35f6333a37542a76a227e3b16acc` |
| Chain | BASE-SEPOLIA |
| USDC contract | `0x036cbd53842c5426634e7929541ec2318f3dcf7e` |
| Circle account | `kmachado618@gmail.com` |
| Auth expiry | 28 days |

## Next: Phase 1 decisions

With the executor-mediated enforcement model confirmed:

1. **Payment policy**: Extend the existing `PolicyEngine` with payment-aware rules (amount caps, payee allowlists) — proven in spike
2. **Golden path flow**: Gemini/ADK ops agent → payment intent → `POST /authorize` → deterministic policy eval → Ed25519 token → `circle wallet transfer` → receipt with settlement tx
3. **x402 endpoint**: Stand up a local x402-paywalled endpoint (the marketplace services are mainnet-only) for the ops agent to discover and pay
4. **Token JTI = idempotency key**: Already proven — single-use nonce prevents replay at both Verigate and Circle layers
