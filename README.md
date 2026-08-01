# Verigate — Circle Agentic Economy Prize Submission

> Submission for the [$50K Circle Agentic Economy Prize](https://www.xprize.org/prizes/build-with-gemini) (Build with Gemini XPRIZE)

## What does this do?

When you give an AI agent a Circle wallet, it can autonomously buy services with USDC. That's powerful but dangerous — a prompt injection or hallucination could drain the wallet.

**Verigate stops AI agents from spending money they shouldn't.**

It sits between the agent and the wallet. Before any payment goes through:

1. **The agent says what it wants to buy** — "I need market data from this service, it costs $0.01, here's the payee address"
2. **Verigate checks the rules** — Is this payee on the approved list? Is the amount under the cap? Is the agent within its rate limit? This check is pure code, no AI — so it can't be tricked.
3. **If approved** — Verigate issues a one-time-use token (expires in 60 seconds), the payment goes through on-chain, and a cryptographic receipt is signed proving what was authorized and what settled.
4. **If denied** — No money moves. A signed denial receipt is created. If the attempt looks malicious (wrong payee + over the cap = possible attack), the Isolator kicks in: it revokes the agent's identity and freezes the wallet.

The AI agent uses Gemini to decide *what* to buy. But the decision of *whether the payment is allowed* is deterministic Python — no LLM involved. You can't prompt-inject your way past a policy engine that doesn't read prompts.

Everything produces a paper trail: Ed25519 signed receipts, hash-chained together, batched into a Merkle tree, anchored to Base. An independent verifier can check the whole chain offline.

## Why not just use Circle's wallet policies?

Circle Agent Wallets already have spending caps, recipient allowlists, and sanctions screening. There IS overlap. So what does Verigate add?

Circle's policies are a **lock on the door**. Verigate is the **security camera, alarm system, and incident response**.

| | Circle Wallet Policies | Verigate |
|---|---|---|
| Block over-cap payments | Yes | Yes |
| Block off-allowlist payees | Yes | Yes |
| **Prove every decision cryptographically** | No — you get tx records, not signed authorization receipts | Yes — Ed25519 signed, hash-chained, Merkle-anchored |
| **Tie the decision to the settlement** | No — the policy and the tx are separate systems | Yes — one receipt proves decision + authorization + on-chain tx |
| **Auto-quarantine a rogue agent** | No — you can manually change policies | Yes — Isolator revokes identity + freezes wallet + produces forensic record |
| **Independently verifiable audit trail** | No — you trust Circle's records | Yes — anyone with the public key can verify offline |
| **Evaluate intent/context** | No — only amount and address | Yes — can evaluate service, reason, rate patterns |

**Circle protects the wallet. Verigate protects the operator.**

The operator is the company that deploys the AI agent — the fintech startup that gives their agent a Circle wallet to autonomously pay for APIs, data feeds, and cloud services. They're responsible for what the agent does, and they're liable if it goes wrong.

Circle stops the money from moving. Verigate proves *why* it moved (or didn't), detects when an agent is compromised, quarantines it automatically, and produces an audit trail that holds up for auditors, regulators, and legal teams:

- **"Prove to our auditor that every payment our agent made was authorized by policy"** — Verigate produces signed authorization receipts, Circle gives you transaction history
- **"Our agent got prompt-injected, show us exactly what happened"** — Verigate has forensic containment records with the exact denial reasons and isolation actions
- **"We need EU AI Act compliance for our autonomous spending system"** — Verigate's Auditor generates compliance reports over real spend data
- **"An engineer changed the policy and the agent overspent — prove the old policy was in effect"** — every receipt is bound to the policy hash that was active when the decision was made

The receipt chain is the real product — not the policy engine.

## Quick Start

### Prerequisites

- Python 3.12+
- [Circle CLI](https://www.npmjs.com/package/@circle-fin/cli): `npm install -g @circle-fin/cli`
- Circle CLI authenticated: `circle wallet login <email> --testnet`
- Gemini API key (optional — falls back to mock agent)

### Run the Demo

```bash
# Clone with submodule
git clone --recursive https://github.com/4KInc/circle-prize-submission.git
cd circle-prize-submission

# Install dependencies
pip install -e ".[dev]"

# Set your Gemini API key (optional)
export GEMINI_API_KEY=your-key-here

# Run the full golden path
make demo
```

This single command:
1. Runs 25 unit tests
2. Gemini agent analyzes a task and forms a payment intent
3. Verigate gate evaluates policy (deterministic, zero-LLM)
4. Approved payment settles real USDC on Base Sepolia
5. Prompt injection attack is blocked pre-settlement
6. Rogue agent is quarantined (identity revoked, wallet frozen)
7. Merkle tree anchored, offline verifier validates everything
8. Dashboard + compliance PDF generated
9. Prints every Basescan URL

### Live Dashboard

```bash
make dashboard
```

Opens a real-time dashboard at `localhost:8080`. Click **Run Golden Path** to watch each step execute live with real USDC settling on Base Sepolia, or **Rogue Agent Demo** to watch three attack scenarios get blocked in real-time.

### Rogue Agent Demo (for video)

```bash
make rogue
```

Three attack scenarios — all blocked, $0.00 lost, agent quarantined.

## Proof Items

| Item | Value |
|------|-------|
| Public repo | [github.com/4KInc/circle-prize-submission](https://github.com/4KInc/circle-prize-submission) |
| Wallet (testnet) | `0x008ed50be2cd35f6333a37542a76a227e3b16acc` on Base Sepolia |
| Wallet (mainnet) | `0x5c34e3e05f0f1b9c4e3b92846791c6516dd431a2` on Base |
| Mainnet tx | [0x47db7910...on Basescan](https://basescan.org/tx/0x47db7910f97e0d39dbea0072af04b30b44bb39d77b40bd0e783790191bbd06bb) |
| Demo command | `make demo` |
| Live dashboard | [verigate-dashboard-1031148889398.us-central1.run.app](https://verigate-dashboard-1031148889398.us-central1.run.app) |
| Dashboard (local) | `make dashboard` (localhost:8080) |

## Architecture

### How it works

```
Gemini Ops Agent                    Verigate Gate                        Circle
                                    (deterministic, zero-LLM)
    "Buy market         ──→    Policy check:                 ──→   circle wallet transfer
     data for                  - Payee on allowlist?                (real USDC settles
     0.01 USDC"                - Amount under cap?                  on Base)
                               - Rate limit OK?
                                      │
                               APPROVE: Ed25519 token
                               (60s, single-use,
                                JTI = idempotency key)
                                      │
                               Sign receipt with
                               settlement tx hash
                               embedded in body
                                      │
                               DENY: signed denial receipt,
                               NO Circle CLI call,
                               Isolator quarantines agent
```

### Enforcement Model

Circle provides no external authorization callback. Our **payment executor** refuses to call the Circle CLI without a valid Verigate token. Circle wallet-layer spending policies (mainnet only) provide an independent second wall.

### Key Properties

- **Zero LLM in the authorization trust path** — policy evaluation is deterministic Python
- **Ed25519 (EdDSA) only** — no HS256 anywhere
- **Per-tenant signing keys** — distinct Ed25519 keypair per tenant
- **Single-use tokens** — 60s TTL, JTI = Circle idempotency key (replay blocked at both layers)
- **Receipt chain** — hash-linked, Ed25519 signed, Merkle-anchored
- **Settlement binding** — tx hash embedded in receipt body (decision + authorization + settlement in one object)

### Components

| Module | Purpose |
|--------|---------|
| `circle/executor.py` | Gated payment executor — policy eval, token issuance, Circle CLI, receipt signing |
| `circle/isolator.py` | Rogue agent containment — revoke identity + freeze wallet + forensic records |
| `circle/verifier.py` | Offline verifier — Ed25519 sigs, hash chain, Merkle proofs, settlement cross-reference |
| `circle/cli.py` | Circle CLI Python wrapper |
| `circle/golden_path.py` | Full demo runner (14 steps) |
| `circle/auditor.py` | Gemini compliance report (EU AI Act + NIST AI RMF) + PDF export |
| `app/` | Live dashboard — FastAPI + SSE streaming |
| `engine/` | Git submodule — [agent-authorization-gateway](https://github.com/4KInc/agent-authorization-gateway) (Apache-2.0) |

### Stack

Python 3.12+ / Ed25519 / SHA-256 / RFC 8785 (JCS) / RFC 6962 Merkle / Circle Agent Stack / Circle CLI / Gemini 2.5 Flash / Base L2

## Tests

```bash
make test
```

25 unit tests covering:
- Policy evaluation (approve/deny paths)
- Payment intent digest binding (deterministic, canonical)
- Replay/nonce+JTI blocking
- Deny path produces signed denial receipt
- Per-tenant key isolation (cross-tenant verification fails)
- Isolator severity classification
- Receipt chain integrity (tamper detection)
- Merkle inclusion proofs

## License

Apache-2.0
