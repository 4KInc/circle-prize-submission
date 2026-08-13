## Inspiration

Most agent-payment demos prove an AI agent *can* spend money. We asked a different question: what if spending money could itself be a risk-mitigation decision?

As AI agents gain spending authority, they face threats that static guardrails can't handle — prompt injection attacks, sanctioned counterparties, behavioral anomalies. Traditional payment controls are binary: allow or block. There's no middle ground, no audit trail, and no way for an insurer to verify that controls were actually enforced.

## What it does

Verigate is a payment-authorization firewall for AI agents. It screens every payment intent against policy limits, live OFAC sanctions data, prompt injection signals, and behavioral baselines — then makes a three-state decision:

- **APPROVE** (score 0-39): Payment is safe. Proceed.
- **STEP_UP** (score 40-74): Uncertain. Autonomously purchase a second opinion from a validator, paying $0.02 USDC, then decide.
- **DENY** (score 75+): Blocked. No money moves.

The STEP_UP mechanism is the core innovation — the system spends real USDC to reduce its own uncertainty before finalizing a decision, with zero human intervention. Every decision produces a cryptographically signed, hash-chained receipt.

## How we built it

- **Risk Engine**: Deterministic Python scorer (no LLM in the auth path) with 6 prompt injection detectors, real OFAC SDN sanctions feed, Shannon entropy analysis, and a behavioral baseline tracker
- **Settlement**: Circle Agent Wallets on Base mainnet, with three segregated wallets (Customer, Treasury, Validator) and real USDC transfers
- **Autonomy**: Background scheduler runs every 30 minutes with no human intervention. A single API call (`POST /api/run/autonomous-single`) executes the full STEP_UP cycle end-to-end
- **Proof Chain**: Ed25519 signed receipts, Merkle-anchored, stored to GCS, with causal chain linking risk score → decision → on-chain settlement

## Challenges we ran into

- Circle's programmable wallet policies are mainnet-only, so testnet development required careful abstraction
- Ensuring the STEP_UP transfer is genuinely autonomous (no human click anywhere in the chain) while still being deterministic and auditable
- Building a risk scorer that's explainable — every score shows exactly which signals contributed and by how much

## What we learned

Circle's Agent Wallet + Gateway stack makes sub-cent micropayments viable in ways that are impossible on card rails ($0.30+ interchange kills any $0.05 transaction). This unlocks an entire category of machine-to-machine economic decisions that simply couldn't exist before.

## What's next

- Third-party validator marketplace (Blockaid, Chainlink oracles as STEP_UP destinations)
- Carrier API for insurers to consume the evidence rail for underwriting AI agent liability policies
- Dynamic risk model training from the behavioral baseline data
