# Verigate — Circle Agentic Economy Prize Submission

> Submission for the [$50K Circle Agentic Economy Prize](https://www.xprize.org/prizes/build-with-gemini) (Build with Gemini XPRIZE)

## The Problem

Your AI agent just spent $50,000 on cloud services at 3am. Your CFO asks: *What did it buy? Who authorized it? Can you prove it to our auditor?*

Today, the answer is logs. Logs can be edited, deleted, or lost. They don't hold up in court. They don't satisfy the EU AI Act. They don't help when an agent gets prompt-injected and tries to drain a wallet.

## What Verigate Does

**Circle controls *whether* agents can pay. Verigate proves *why* they did.**

Every time an AI agent makes a payment through Circle, Verigate produces a signed receipt — a single object that binds the agent's identity, the policy that was evaluated, and the settlement transaction. These receipts are hash-chained, Merkle-anchored, and independently verifiable by any third party, offline, forever.

If an agent goes rogue, Verigate catches it before the money moves, documents exactly what happened, and publishes the incident to an on-chain reputation registry.

## Python SDK

```python
from verigate import Gate, Intent

gate = Gate("circle://agent-wallet", allowed_payees=["0xabc..."], max_amount=1.0)
receipt = gate.authorize(Intent(payee="0xabc...", amount=0.01, service="market-data"))
gate.verify()  # PASS — signatures, hash chain, merkle all verified
```

Every `authorize()` call produces a signed receipt with settlement tx binding. Every `verify()` runs full offline verification. No network needed. See [`run_sdk_demo.py`](run_sdk_demo.py) for a complete end-to-end example with real USDC.

## The Business

**Customer:** Any company using AI agents to spend money. Today that's crypto-native startups and DeFi protocols. By 2027, it's every enterprise running agentic workflows — procurement, media buying, cloud infrastructure, freelancer payments.

**Revenue model:** Per-receipt pricing. A company running 100 agents making 1,000 payments/day generates 30,000 receipts/month.

**Why Circle:** Verigate can't exist without Circle. Without Circle wallets, there's no payment. Without Circle CLI, there's no settlement. Without Agent Marketplace, there's no service discovery. Circle is the infrastructure. Verigate is the audit layer on top.

## How It Works

1. **Agent presents x401 credential** — proves a verified human authorized it with scoped permissions
2. **Gate evaluates policy** — deterministic Python, zero-LLM, immune to prompt injection
3. **If approved** — payment settles via Circle CLI, receipt signed AFTER settlement with tx hash embedded
4. **If denied** — signed denial receipt produced, forensic analysis triggered, ERC-8004 reputation event published on-chain

## Circle Integration

Circle's Agent Stack provides the infrastructure (wallets, spending caps, Action Gate, MPC co-signing). Verigate adds what Circle doesn't have: **cryptographic proof**.

| What | Circle | Verigate |
|---|---|---|
| **Enforcement** | Action Gate blocks bad payments | Deterministic second wall (defense in depth) |
| **Audit trail** | Internal records | Signed, hash-chained, Merkle-anchored receipts |
| **Incident response** | MicroVM isolation | Forensic evidence + ERC-8004 reputation on-chain |
| **Compliance** | Transaction history | Automated EU AI Act / NIST AI RMF reports |
| **Disputes** | N/A | Exportable proof chain for third-party arbiters |

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
| ERC-8004 contract | [0xf5FE7BF0...on Basescan](https://sepolia.basescan.org/address/0xf5FE7BF0163328BA0011Fa49Caf3707434E145AA) on Base Sepolia |
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
- **x401 identity binding** — verifiable credential hash embedded in every receipt (WHO authorized)
- **Ed25519 (EdDSA) only** — no HS256 anywhere
- **Per-tenant signing keys** — distinct Ed25519 keypair per tenant
- **Single-use tokens** — 60s TTL, JTI = Circle idempotency key (replay blocked at both layers)
- **Receipt chain** — hash-linked, Ed25519 signed, Merkle-anchored
- **Settlement binding** — tx hash embedded in receipt body (identity + decision + authorization + settlement in one object)
- **ERC-8004 reputation** — isolation events published to on-chain registry for portable trust
- **Cross-agent correlation** — forensic analysis detects systemic attacks across agents
- **Dispute resolution** — exportable chain verifiable by third-party arbiters offline

### Components

| Module | Purpose |
|--------|---------|
| `circle/executor.py` | Gated payment executor — x401 verification, policy eval, token issuance, Circle CLI, receipt signing |
| `circle/x401.py` | x401 credential issuance + verification — binds agent identity into receipt chain |
| `circle/isolator.py` | Forensic recorder — signed incident evidence + findings + recommendations for Circle's Action Gate |
| `circle/reputation.py` | ERC-8004 reputation writer — publishes isolation events to on-chain registry |
| `circle/correlation.py` | Cross-agent forensic correlation — detects systemic attacks across multiple agents |
| `circle/verifier.py` | Offline verifier — Ed25519 sigs, hash chain, Merkle proofs, x401 binding, settlement cross-reference |
| `circle/dispute.py` | Dispute resolution — export chain + standalone third-party verifier CLI |
| `circle/auditor.py` | Gemini compliance report (EU AI Act + NIST AI RMF) + PDF export |
| `circle/cli.py` | Circle CLI Python wrapper + Recibo bi-directional settlement binding |
| `circle/golden_path.py` | Full demo runner (16 steps) |
| `app/` | Live dashboard — FastAPI + SSE streaming |
| `engine/` | Git submodule — [agent-authorization-gateway](https://github.com/4KInc/agent-authorization-gateway) (Apache-2.0) |

### Stack

Python 3.12+ / Ed25519 / SHA-256 / RFC 8785 (JCS) / RFC 6962 Merkle / x401 / ERC-8004 / Recibo / Circle Agent Stack / Circle CLI / Gemini 2.5 Flash / Base L2

## How Gemini Is Used

Gemini is not just bolted on — it's used where LLM reasoning adds genuine value:

| Where | What Gemini Does | Why Not Deterministic Code |
|---|---|---|
| **Ops Agent** | Analyzes task, discovers services, forms payment intent | Requires reasoning about task requirements vs available services |
| **Forensic Recorder** | Deep analysis of attack vectors from denial patterns | Pattern matching finds the WHAT; Gemini explains the HOW and WHY |
| **Auditor** | EU AI Act / NIST AI RMF compliance narrative | Regulatory language requires contextual reasoning, not templates |
| **Compliance Report** | Executive summary over real USDC spend data | Synthesizes findings across receipts, denials, and incidents |

The authorization decision is **never** LLM-powered — that's deterministic Python. Gemini handles analysis and reporting where reasoning adds value.

## Limitations & Honest Assessment

We believe in being transparent about what this demo does and doesn't do:

| Feature | Status | What It Proves |
|---|---|---|
| **Receipt chain** | Real — Ed25519 signed, hash-chained, Merkle-anchored | Core innovation, fully functional |
| **Settlement binding** | Real — tx hash from actual USDC transfer on Base Sepolia | Receipts reference real on-chain transactions |
| **Public key anchoring** | Real — wallet signs the JWK hash on-chain | Verifiers can trust the public key without trusting the operator |
| **x401 credentials** | Protocol-compatible stub | Architecture is ready; swap for real x401 SDK when available |
| **ERC-8004 reputation** | Real — deployed contract on Base Sepolia | [Contract on Basescan](https://sepolia.basescan.org/address/0xf5FE7BF0163328BA0011Fa49Caf3707434E145AA). Real on-chain txs. |
| **Recibo binding** | Protocol-compatible stub (standard transfer on testnet) | Ready for Recibo contract; bi-directional binding is architectural |
| **Demo payee** | Self-pay (agent wallet pays to same-operator address) | Testnet limitation; the x402 flow and receipts are real |
| **Scale** | Demo-scale (linear chain) | Production would use epoch-based checkpointing with Merkle anchors |
| **Forensic recommendations** | Text output (no Circle API integration) | Circle would need to expose an Action Gate policy update API |

### What Circle could build themselves

Circle could add Ed25519 signatures to their Action Gate audit records. The technical barrier is low. Our moat is not "signatures" — it's the **full chain**: hash-linked receipts + settlement binding + policy hash binding + Merkle anchoring + x401 identity binding + offline verification + dispute resolution + forensic analysis + cross-agent correlation + ERC-8004 reputation publishing. That's a system, not a feature.

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
- Forensic severity classification
- Receipt chain integrity (tamper detection)
- Merkle inclusion proofs

## License

Apache-2.0
