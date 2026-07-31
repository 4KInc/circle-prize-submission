# Verigate — Circle Agentic Economy Prize Submission

**Deterministic AI Agent Payment Authorization for Circle Agent Stack**

> Submission for the [$50K Circle Agentic Economy Prize](https://www.xprize.org/prizes/build-with-gemini) (Build with Gemini XPRIZE)

## What is this?

AI agents that can spend money autonomously are dangerous — a prompt injection or hallucination can drain funds. Verigate is a **deterministic, zero-LLM authorization gateway** that sits between an AI agent and Circle's Agent Wallets. Every USDC payment must pass through the gate before it can settle on-chain. If the gate says no, the money doesn't move.

### The Demo

A **Gemini-powered ops agent** autonomously purchases a service using USDC via Circle Agent Stack. Verigate's deterministic gate authorizes every payment pre-settlement, binds a signed receipt to the exact payment authorization, and contains the agent if it goes rogue.

```
Gemini Ops Agent → Payment Intent → Verigate Gate → Circle CLI → USDC Settles on Base
                                         │
                                    Zero-LLM Policy
                                    (payee allowlist,
                                     amount cap,
                                     rate limit)
```

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

# Run the full golden path (Phases 1-4)
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

### Run the Rogue Agent Demo (for video)

```bash
make rogue
```

Three attack scenarios — all blocked, $0.00 lost, agent quarantined.

## Proof Items

| Item | Value |
|------|-------|
| Public repo | [github.com/4KInc/circle-prize-submission](https://github.com/4KInc/circle-prize-submission) |
| Wallet address | `0x008ed50be2cd35f6333a37542a76a227e3b16acc` |
| Chain | Base Sepolia (parametrized for Base mainnet) |
| Demo command | `make demo` |

## Architecture

### Enforcement Model: Executor-Mediated

Circle provides no external authorization callback. Our **payment executor** refuses to call the Circle CLI without a valid Verigate token. Circle wallet-layer spending policies (mainnet only) provide an independent second wall.

```
┌─────────────────────────────────────────────────────────────────┐
│                    VERIGATE AUTHORIZATION                       │
│                                                                 │
│  Payment Intent ──→ Policy Engine ──→ Ed25519 Token ──→ Receipt │
│  {payee, amount}    (deterministic,    (60s, single-use,        │
│                      zero-LLM)         JTI = idempotency key)   │
│                                                                 │
│  DENY: signed denial receipt, NO Circle CLI call                │
│  APPROVE: token issued, Circle CLI called, USDC settles         │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   CIRCLE WALLET    │
                    │  (second wall)     │
                    │  spending policies │
                    │  (mainnet only)    │
                    └───────────────────┘
```

### Key Properties

- **Zero LLM in the authorization trust path** — policy evaluation is deterministic Python
- **Ed25519 (EdDSA) only** — no HS256 anywhere
- **Per-tenant signing keys** — distinct Ed25519 keypair per tenant
- **Single-use tokens** — 60s TTL, JTI = Circle idempotency key (replay blocked at both layers)
- **Receipt chain** — hash-linked, Ed25519 signed, Merkle-anchored
- **Settlement binding** — tx hash embedded in receipt body (decision → authorization → settlement in one object)

### Components

| Module | Purpose |
|--------|---------|
| `circle/executor.py` | Gated payment executor — policy eval → token → Circle CLI → receipt |
| `circle/isolator.py` | Rogue agent containment — revoke identity + freeze wallet |
| `circle/verifier.py` | Offline verifier — sigs, chain, Merkle, settlement cross-reference |
| `circle/cli.py` | Circle CLI Python wrapper |
| `circle/golden_path.py` | Full demo runner (14 steps, Phases 1-4) |
| `circle/dashboard.py` | HTML money dashboard |
| `circle/auditor.py` | Gemini compliance report + PDF export |
| `engine/` | Git submodule — [agent-authorization-gateway](https://github.com/4KInc/agent-authorization-gateway) (Apache-2.0) |

### Stack

Python 3.12+ · Ed25519 · SHA-256 · RFC 8785 (JCS) · RFC 6962 Merkle · Circle Agent Stack · Circle CLI · Gemini 2.5 Flash · Base L2

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
