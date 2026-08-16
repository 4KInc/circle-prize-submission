## Inspiration

AI agents are getting spending authority. Circle Agent Wallets let them hold USDC and pay for services autonomously. But every other agent payment demo answers the same question: "can an agent spend money?"

We asked a different one: **what if spending money could itself be a risk-mitigation decision?**

When an agent is uncertain whether a payment is safe, it can't just block it (loses the opportunity) or approve it (risks the loss). Verigate introduces a third option: **spend a small amount of USDC to purchase independent evidence, then decide.** That's the STEP_UP mechanism — an agent that autonomously buys intelligence to reduce its own uncertainty, with zero human intervention.

## What it does

Verigate is a payment-screening agent for AI agents. Before your agent executes a USDC payment via Circle Agent Wallets, POST the intent to Verigate:

- **APPROVE** (score 0-39): Payment is safe. Proceed.
- **STEP_UP** (score 40-74): Uncertain. Verigate autonomously pays $0.02 USDC from its Treasury wallet to an independent Validator for a second opinion (real on-chain USDC transfer), then decides.
- **DENY** (score 75+): Blocked. Governance intelligence returned — root cause, attack vector, containment actions, policy recommendations.

Risk scoring checks OFAC sanctions (live SDN feed), prompt injection patterns (6 detectors), behavioral anomalies (z-score deviation from agent baseline), and amount/payee policy violations.

**Three products, all settled in USDC:**
- **Screening** ($0.05): Decision + risk breakdown + forensic summary
- **Governance** ($0.15): Full forensic analysis + recommendations with rationale
- **Evidence** ($0.25): Full signed proof bundle for carrier underwriting

Every decision produces an Ed25519-signed, hash-linked receipt anchored to BASE mainnet.

## How we built it

**Risk Engine:** Deterministic Python scorer with 6 prompt injection detectors, live OFAC SDN sanctions feed (auto-refreshed every 12h), Shannon entropy analysis, behavioral baseline tracker, and per-signal contribution breakdown. No LLM in the scoring path — the risk score is reproducible and explainable.

**Gemini Integration (6 structural roles):**
1. STEP_UP validator reasoning — Gemini evaluates evidence and returns CONFIRM/DENY with confidence
2. RAG knowledge base — Gemini embeddings (embedding-001) store every screening decision; before STEP_UP reasoning, the validator retrieves relevant past events via cosine similarity so Gemini reasons over history, not just the current case
3. Policy synthesis — natural language to Circle Agent Wallet policies
4. Cross-agent scope negotiation — Gemini mediates between two agents' policy requirements
5. Governance agents — Investigator (forensics), Auditor (compliance), Recommender (policy proposals) run on every DENY
6. Carrier self-wake — Gemini decides if a DENY event is worth $0.25 to investigate

**Circle Agent Stack (5/5 components):**
- 3 Circle Agent Wallets (Customer, Treasury, Validator) with programmable spending policies
- Circle Gateway nanopayments for gas-free x402 fee settlement
- Circle CLI for wallet creation, policy management, USDC transfers
- x402 protocol for paywalled endpoints
- MCP server at verigate.cloud/mcp

**Settlement:** Real USDC on Base mainnet. Three verified transactions:
- [$0.05 screening fee](https://basescan.org/tx/0x5db4466814dd16e56e35ee1aa60470c321dba6daff65cfca56ce5130e4249c58) (Customer → Treasury)
- [$0.02 STEP_UP evidence](https://basescan.org/tx/0xdfcd6729a28fe7c6f476608b242fae38418b13dfde51b18de007db82aa76f732) (Treasury → Validator)
- [$0.10 treasury funding](https://basescan.org/tx/0x958f2c400d0f955dc02678ff1172cd055305842f18d32a73386e295af59b5) (Customer → Treasury)

**Proof Chain:** Ed25519 signed receipts, Merkle-anchored, stored to GCS, independently verifiable offline with `python -m circle.dispute verify export.json`.

**Infrastructure:** FastAPI on GCP Cloud Run, 163 passing tests (15 test files), CI-enforced (ruff + mypy + pytest).

## Challenges we ran into

**Autonomous STEP_UP is hard.** Ensuring the Treasury→Validator USDC transfer is genuinely autonomous (no human click anywhere in the chain) while remaining deterministic and auditable required careful separation of the decision path (scorer) from the execution path (Circle CLI). The evidence fee scales dynamically with transaction value: `max($0.02, min(amount × 0.1%, $5.00))`.

**Circle wallet policies are mainnet-only.** Testnet development required abstracting the policy layer so the same code runs against both BASE-SEPOLIA and BASE mainnet with a single env var toggle.

**Governance output monetization gap.** On every DENY, Gemini runs three governance agents (~$0.004 cost). If the carrier doesn't pull the evidence, that cost is wasted. We solved this with a governance tier ($0.15) that lets enterprise agents buy the full forensic output directly.

**Replay attacks on the enforcement loop.** A compromised agent resending denied intents could rack up Gemini costs. We built a replay detection + circuit breaker system: replays are free (no re-scoring), 5 denials → throttle, 10 → suspend.

## Accomplishments that we're proud of

- **Real USDC on mainnet** — not testnet tokens, not simulated. Three verified transactions on Base.
- **STEP_UP is genuinely novel** — no other payment screening system autonomously spends money to reduce its own uncertainty before deciding.
- **163 tests passing** — including 5 async concurrency tests, replay/breaker enforcement tests, and end-to-end STEP_UP cycle tests.
- **Three revenue surfaces** — screening ($0.05), governance ($0.15), evidence ($0.25). Every piece of output has a buyer.
- **Listed on Circle Agent Marketplace** — submitted for listing so other agents can discover and pay for Verigate's screening service.
- **Early-stage integration conversations with BlockRun** (Circle OpenClaw hackathon winner) about using Verigate as middleware for x402-routed agent payments.
- **4 insurance carrier conversations** — Breach Insurance (CEO-level), Relm Insurance (shadow-mode pilot agreed), Risk Collective/Lloyd's syndicate (vendor panel candidacy), Native/Lloyd's broker (technical docs requested).

## What we learned

Circle's Agent Wallet + Gateway stack makes sub-cent micropayments viable in ways impossible on card rails ($0.30+ interchange kills any $0.05 transaction). This unlocks machine-to-machine economic decisions that couldn't exist before — an agent spending $0.02 to buy evidence is economically rational only because the payment rail costs effectively zero.

Gemini's strength isn't replacing deterministic controls — it's reasoning about context that rules can't capture. Our prompt injection regex catches "OVERRIDE" patterns. Gemini catches "this sounds like a CEO impersonation using urgency framing to bypass approval." The two layers are complementary, not competing.

## What's next for Verigate

- **BlockRun integration** — Verigate as screening middleware for x402-routed agent payments
- **Third-party validator marketplace** — Blockaid, Chainlink oracles as STEP_UP evidence sources
- **Carrier design partner** — first insurance carrier consuming the evidence rail for AI agent liability underwriting
- **ERC-8004 reputation registry** — on-chain agent reputation events from DENY/isolation decisions
