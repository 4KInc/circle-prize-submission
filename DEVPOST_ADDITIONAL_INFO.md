# DevPost Additional Info - Field-by-Field Answers

## Upload a File
Upload the demo video (when ready) or a PDF of the architecture diagram.

## What date did you start this project?
`05-19-26`

## Submitter type
`Individual` (or `Team` if you have teammates)

## Country of residence
`United States`

## Which Category are you submitting into?
Pick the category that best fits - likely "Security & Safety" or "Financial Services" depending on what's available. Check the dropdown options.

---

## Explain how your project uses AI to impact the world

Verigate uses Gemini AI to make autonomous agent payments safe. As AI agents gain spending authority - holding USDC wallets and paying for services without human approval - the risk of fraud, prompt injection, and sanctions violations grows exponentially. No human is watching every $0.05 payment an agent makes.

Verigate sits between the agent and the payment. Before any USDC moves, Gemini-powered risk scoring evaluates the intent against OFAC sanctions, injection patterns, behavioral anomalies, and policy rules. When uncertain, Verigate autonomously spends $0.02 USDC to purchase independent evidence from a validator - spending money to reduce risk before finalizing.

The impact: every AI agent with a Circle wallet can now transact safely, with cryptographic proof that controls were enforced. This enables enterprises, regulators, and insurers to trust autonomous agent payments - unlocking the agentic economy at scale.

---

## How do you measure impact?

Theory of change: As AI agents handle more financial transactions, the absence of payment-level controls will produce fraud losses, regulatory violations, and enterprise distrust. Verigate provides the missing control layer.

Hypotheses:
1. Enterprises will not give agents spending authority without auditable controls
2. Insurers cannot underwrite AI agent liability without verifiable evidence of control enforcement
3. Per-payment screening at $0.05 is economically viable because Circle's zero-gas USDC rails make sub-cent transactions possible

Outputs measured:
- Payments screened (163 test scenarios verified)
- DENY rate and false positive rate
- STEP_UP evidence purchase rate (~25% of checks)
- Carrier pull rate (conversion from DENY events to paid evidence)
- Real USDC transactions on Base mainnet (3 verified)

Outcomes expected:
- Short-term: Enterprise agents adopt Verigate screening before every payment
- Long-term: Insurance carriers use the evidence rail for AI agent liability underwriting
- Proof of success: paying customers, carrier LOIs, and ecosystem integrations (BlockRun conversations initiated)

---

## Explain the underlying business model

B2B - three products, three payers:

1. Screening ($0.05/check) - Enterprise agents pay per payment screened. High volume, thin margin. This is the top of the funnel.
2. Governance ($0.15/check) - Enterprise agents pay for full forensic analysis + actionable recommendations with rationale. 3x the screening fee for 3-5x the intelligence value.
3. Evidence ($0.25/pull) - Carrier agents pay for the full signed proof bundle for underwriting. Paid via x402 Circle Gateway nanopayments.

All payments settle in USDC on Base mainnet via Circle Agent Wallets. No monthly minimums, no signup - pure pay-per-use.

Customer acquisition: Listed on Circle Agent Marketplace. Agents discover Verigate through the marketplace directory and pay via x402. In early integration conversations with BlockRun (Circle OpenClaw hackathon winner) - BlockRun routes agent payments to external APIs and services via x402, and every outbound payment they route is a payment Verigate can screen. One POST to /api/check before each x402 settlement. If Verigate flags it, BlockRun doesn't route it. This positions Verigate as the security middleware layer for the entire x402 routing ecosystem.

Retention: Every payment screened produces a signed receipt. The receipt chain builds cumulative value - compliance reports, audit trails, carrier evidence - that increases switching costs over time.

---

## How will you sustain business operations in the future?

Resource allocation:
- Infrastructure: ~$21/month (GCP Cloud Run + GCS + Gemini API)
- Revenue per check: $0.05 USDC
- Break-even: ~1,500 checks/day (Product 1 alone covers all costs)
- 90% gross margin at observed STEP_UP rate (~25%)

Threats:
- Circle could build native payment screening (mitigation: Verigate's Gemini-powered reasoning and carrier evidence rail are differentiated features Circle doesn't offer)
- Carrier-pays hypothesis is early-stage (mitigation: 4 carrier conversations - Breach Insurance, Relm Insurance, Risk Collective/Lloyd's, Native/Lloyd's - validate demand; screening revenue is self-sustaining without carrier revenue)

Post-hackathon operations:
- Apply to Circle's ecosystem fund for growth capital
- Pursue BlockRun integration as first distribution channel - every payment BlockRun routes to external APIs and services via x402 is a payment Verigate screens, making BlockRun a volume multiplier for screening revenue
- Onboard first carrier design partner for evidence rail validation
- Scale to volume pricing ($0.02/check at >1,000 checks/day)

---

## Which AI tools have you leveraged?

- Google Gemini 2.5 Flash - 6 structural roles: STEP_UP validator reasoning, RAG embeddings + retrieval (embedding-001), policy synthesis, cross-agent negotiation, governance agents (forensics + compliance + recommendations), carrier self-wake decision
- Claude Code (Anthropic) - Development assistant for codebase implementation
- Google Cloud Platform - Cloud Run (hosting), GCS (proof bundle storage)

---

## Explain how your business model is sustainable and viable

Five-year goal:
- Year 1: 10,000 checks/day → $182K ARR (screening only)
- Year 3: 100,000 checks/day + governance tier + carrier pulls → $2M ARR
- Year 5: 1M checks/day, enterprise contracts → $10M+ ARR
- TAM: Every AI agent with a wallet needs payment screening. Circle alone has 200M+ USDC wallets.

Path to profitability:
- Already profitable per-unit: $0.05 revenue, ~$0.005 variable cost = 90% gross margin
- Infrastructure cost: ~$21/month
- Break-even at ~1,500 checks/day (~$75/day revenue)
- No burn rate - the product is live and self-sustaining at any volume

Evidence of product-market fit:
- BlockRun (Circle OpenClaw winner) - we reached out, their Growth Lead (Rami) responded with interest and scheduled a call
- Listed on Circle Agent Marketplace for agent discovery
- 4 carrier conversations validating the evidence rail:
  - Breach Insurance - CEO-level engagement on AI agent liability
  - Relm Insurance - shadow-mode pilot agreed
  - Risk Collective (Lloyd's syndicate) - vendor panel candidacy
  - Native (Lloyd's broker) - technical docs requested
- 163 passing tests across 15 test files - production-grade, not a prototype
- Real USDC on Base mainnet - not testnet tokens

---

## Please explain how your business operates with AI

Verigate is AI-native in its core loop:

1. Gemini makes the STEP_UP decision - when the deterministic scorer is uncertain (score 40-74), Gemini evaluates the evidence and returns CONFIRM or DENY with confidence
2. RAG knowledge base (Gemini embedding-001) - every screening decision is embedded and stored. Before STEP_UP reasoning, the validator retrieves the 5 most relevant past events (same agent history + cross-agent anonymized cases) via cosine similarity. Gemini reasons over current context + retrieved history, not in isolation. The system learns from past decisions without model retraining.
3. Gemini generates governance intelligence - on every DENY, three Gemini-powered agents run: Investigator (forensic root cause), Auditor (EU AI Act + NIST compliance), Recommender (policy change proposals)
4. Gemini decides carrier self-wake - autonomous carrier agent uses Gemini to evaluate each DENY event: "is this worth $0.25 to investigate?"
5. Gemini synthesizes policies - natural language to Circle Agent Wallet spending policies
6. Gemini negotiates scope - two agents propose policies, Gemini mediates

Without Gemini, Verigate is a binary allow/block gate. With Gemini, it reasons about context, retrieves historical evidence, buys new evidence, generates forensic intelligence, and makes autonomous economic decisions. Remove Gemini and the RAG pipeline collapses - no embeddings, no retrieval, no learning.

---

## Please explain the extent to which AI is live in production

Gemini is live in production at verigate.cloud, executing key decisions:

1. STEP_UP verdict - Gemini determines whether to CONFIRM or DENY a payment after evidence is purchased. This directly controls whether USDC moves.
2. RAG retrieval - Before STEP_UP reasoning, Gemini embedding-001 embeds the query, retrieves the top-K most similar past screening events from the knowledge base, and feeds them as context to the reasoning model. Live at GET /api/rag/stats (shows records, embeddings, feedback counts). Verified: autonomous-single returns rag_records_retrieved and rag_context_used in the validator verdict.
3. Governance pipeline - Gemini generates forensic analysis, compliance reports, and policy recommendations on every DENY. These are the $0.15 governance product.
4. Carrier self-wake - Gemini autonomously decides whether to investigate denied payments at $0.25 cost. This is a real spending decision - the carrier agent uses Gemini to evaluate economic rationality.
5. Policy synthesis - live endpoint at POST /api/synthesize-policy
6. Scope negotiation - live endpoint at POST /api/negotiate-scope

All six roles are deployed on GCP Cloud Run and callable via the live API.

---

## Google Cloud products used

- Google Cloud Run - hosts the Verigate dashboard and API (verigate.cloud)
- Google Cloud Storage (GCS) - stores signed proof bundles, evidence artifacts, and behavioral history
- Google Gemini API (via google-genai SDK) - 6 structural AI roles in the payment screening pipeline (including Gemini embedding-001 for RAG)

---

## LLMs used and Gemini API usage

LLMs used: Google Gemini 2.5 Flash exclusively for all AI reasoning.

Gemini API usage (6 structural roles):
1. `circle/validator_gemini.py` - STEP_UP evidence reasoning. Gemini evaluates payment intent + risk signals + RAG-retrieved history and returns CONFIRM/DENY with confidence score and red flags.
2. `circle/rag_store.py` - RAG knowledge base. Uses Gemini embedding-001 to embed every screening decision. Before STEP_UP reasoning, retrieves the top-K most similar past events via cosine similarity. Gives Gemini memory across decisions.
3. `circle/policy_synthesis.py` - Natural language to Circle Agent Wallet policy. Gemini generates structured spending rules from plain English descriptions.
4. `circle/negotiation.py` - Cross-agent scope negotiation. Gemini mediates between two agents' policy requirements and proposes compromises.
5. `circle/agents.py` - Three governance agents (Investigator, Auditor, Recommender). Each makes a Gemini call to analyze denied payment events.
6. `circle/carrier_agent.py` - Carrier self-wake. Gemini evaluates each DENY event and decides if it's worth $0.25 to investigate.

No other LLM is used anywhere in the project. The deterministic risk scorer uses no LLM - only Gemini for reasoning and embedding tasks.

---

## GitHub repo URL
`https://github.com/4KInc/verigate`

---

## Evidence of project running
Upload:
1. GCP Cloud billing invoice PDFs (May-Aug 2026)
2. Gemini API observability dashboard screenshot
3. Cloud Run metrics screenshot
4. Basescan transaction screenshots

---

## I confirm GitHub repo is shared
Yes - repo is public at github.com/4KInc/verigate

---

## Pre-existing business resources
Yes. BlockIntel Inc was incorporated before May 19, 2026. The entity existed but had no product, no customers, no revenue, and no code related to Verigate prior to the hackathon. Verigate was conceived and built entirely during the hackathon period. No existing employees, customer relationships, audience, followers, or partnerships were used.

---

## Total Revenue
`$0`

(No external paying customers yet. All mainnet USDC transactions are internal demo flows between Verigate's own wallets proving the mechanism works.)

---

## Revenue by Month
`May: $0, June: $0, July: $0, August: $0`

---

## Explain the revenue
No external revenue during the hackathon period. The three mainnet USDC transactions ($0.05 screening fee, $0.02 STEP_UP evidence, $0.10 treasury funding) are internal transfers between Verigate's own Circle Agent Wallets, demonstrating the payment mechanism. The product is live and functional - it screens payments, moves USDC, and produces signed receipts - but has not yet acquired paying third-party customers.

---

## Related-Party Revenue
`$0`

---

## Total Expenses
`~$150`

---

## Explain the expenses
1. COGS (0%): $0 - no goods sold yet
2. Sales and marketing (0%): $0 - no paid marketing
3. Research and development (90%): ~$135 - GCP Cloud Run hosting (~$15/month x 3 months), Gemini API usage (~$15/month x 3 months), domain registration (verigate.cloud), USDC for mainnet testing
4. General and administrative (10%): ~$15 - incorporation filing (BlockIntel Inc)

Primary driver: infrastructure costs for running the live production service on GCP Cloud Run + Gemini API calls during development and testing.

---

## Total COGS
`$0`

---

## Explain COGS
No goods or services sold to external customers during the hackathon period. COGS will be Gemini API costs (~$0.004/DENY for governance agents) + GCS storage (~$0.0001/bundle) once serving paying customers.

---

## Total marketing and customer acquisition expense
`$0`

---

## Explain marketing expenses
No paid marketing or advertising. Customer acquisition has been organic:
- Listed on Circle Agent Marketplace (free submission)
- Reached out to BlockRun (Circle OpenClaw winner), their Growth Lead scheduled a call to discuss integration
- GitHub repo is public

---

## Additional Expenses
GCP infrastructure (~$45), Gemini API usage (~$45), domain registration (~$15), USDC for mainnet testing (~$0.17), state incorporation filing (~$45).

---

## Number of users acquired
`0` (no external users yet - product is live but pre-launch)

---

## Number of paying users
`0`

---

## Verifiable testimonial
No public testimonial yet. However, active conversations with 5 organizations validate market interest:
- BlockRun (Circle OpenClaw winner) - we reached out, their Growth Lead (Rami) responded and scheduled a call to discuss integration
- Breach Insurance - CEO-level engagement on AI agent liability underwriting
- Relm Insurance - shadow-mode pilot agreed for evidence rail
- Risk Collective (Lloyd's syndicate) - vendor panel candidacy for AI risk data
- Native (Lloyd's broker) - requested technical documentation for carrier API

---

## Level of learning
Select: "Significant - I/we learned a great deal and grew substantially" (or equivalent highest option)

---

## P&L Upload
Generate a simple P&L PDF using the template at bit.ly/4w3DvwL

```
Revenue:           $0
COGS:              $0
Gross Profit:      $0
Operating Expenses:
  R&D:             $135
  Sales/Marketing: $0
  G&A:             $15
Total OpEx:        $150
Net Income:        -$150
```

---

## Agentic Economy Prize - Opt in
`I confirm`

## Agentic Economy Prize - GitHub repo
`https://github.com/4KInc/verigate`

## Agentic Economy Prize - Circle wallet address
`0x0c744ecb3949b3582cdd2dbc70dc876405eec44d` (Treasury wallet - receives screening fees and pays for evidence)

## Agentic Economy Prize - Block explorer URL
`https://basescan.org/tx/0xdfcd6729a28fe7c6f476608b242fae38418b13dfde51b18de007db82aa76f732`
(STEP_UP evidence purchase - Treasury → Validator, $0.02 USDC, autonomous, no human in the loop)
