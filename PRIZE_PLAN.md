# Verigate - Circle Agentic Economy Prize Action Plan

> Consolidated from two strategic reviews. Deadline: Aug 17, 2026, 1:00 PM PT (~6 days).

## Critical Context

The Circle Agentic Economy Prize is **winner-take-all**: one team, $50,000, judged exclusively by Circle. Devpost forwards opted-in submissions; Circle reviews and picks independently. There is no second place.

Circle's four scoring criteria do **not** mention revenue, customer count, or business traction. They score on the elegance, autonomy, and centrality of the agentic-payment mechanism itself. The insurance/carrier angle is valuable narrative context but is not what Circle is scoring on.

## The #1 Disqualification Risk

Circle's eligibility rules state: **"a human manually completing checkout does not qualify."**

The current "Try It" tab has a human typing a payee, amount, and reason, then clicking "Check Payment." A strict reading could disqualify the submission. The fix is not removing the Try It tab (it's a valuable testing tool), but ensuring the **video and written submission** make it unmistakable that:

1. The triggering event originates from agent logic (scheduler), not a human typing into a form
2. The STEP_UP evidence purchase executes with no human click between "Verigate detects uncertainty" and "Treasury pays validator"
3. The final settlement occurs without a human authorizing the specific amount or counterparty

The background scheduler (running every 30 min) IS the proof of autonomy. The Try It tab is a testing/exploration interface. The video must show both but lead with the scheduler.

---

## Priority 1: Code Changes (Days 1-2)

### 1a. Operator Dashboard View (CX criterion - weakest, 25% of score)

**Problem:** Circle asks "how well does the integration deliver a great experience for the end user?" The current dashboard is developer-facing. The "Autonomous Operations" card is a good start but needs to be the hero element.

**Change:** Build a single clean operator-facing summary screen (or enhance the existing overview card) showing:
- Total agent payments screened
- Payments blocked (with $0 lost)
- Evidence purchases made autonomously
- Days running unattended
- Last check result and time
- System health (all agents active, receipt chain intact)

A non-technical judge should look at this for 5 seconds and understand: "This system has been protecting agent wallets autonomously for 8 days."

**Files:** `app/static/index.html`, `app/scheduler.py`, `app/server.py`

**Done when:** A judge landing on the overview page sees operational metrics from real autonomous activity without clicking anything.

### 1b. Scheduler Makes Real Testnet Transfers

**Problem:** The scheduler currently runs risk-scoring-only (no USDC transfers). The docstring honestly says so. But "continuous autonomous operation" is stronger when it means real USDC movement, not just log entries.

**Change:** On each scheduler run, if the testnet wallet has sufficient balance (>$0.20):
- Execute a real $0.05 fee transfer (Customer -> Treasury)
- If the check results in STEP_UP, execute a real $0.02 transfer (Treasury -> Validator)
- Store the receipt with real settlement tx hashes
- Guard: skip transfers if balance < $0.20, max 48 real transfers/day

**Files:** `app/scheduler.py`, `circle/cli.py`

**Done when:** GCS bundles from scheduler runs contain real testnet tx hashes viewable on Basescan. The Autonomous Operations card shows real earned/spent from actual transfers.

### 1c. Dynamic STEP_UP Pricing

**Problem:** The $0.05 fee and $0.02 evidence cost are static. A $10,000 transaction warrants deeper evidence than a $0.50 one. Static pricing undermines the "intelligent" claim.

**Change:** Scale the evidence cost dynamically:
```python
evidence_fee = max(0.02, min(float(amount) * 0.001, 5.00))
```

The base fee ($0.05) stays fixed. The evidence cost scales with the transaction value. Document this in ECONOMICS.md and surface it in the receipt's `step_up.verification_budget_usdc`.

**Files:** `circle/executor.py`, `ECONOMICS.md`

**Done when:** A $1000 payment triggers a $1.00 evidence purchase; a $0.50 payment triggers $0.02. The receipt records the actual cost.

### 1d. Eligibility Checklist in README

**Problem:** Circle screens for eligibility before scoring on the four criteria. A judge under time pressure benefits from not having to hunt for eligibility proof.

**Change:** Add immediately after the Judge's Path table:

```
## Eligibility Confirmation

| Requirement | Evidence |
|-------------|----------|
| Uses Circle Agent Stack | Agent Wallets, Gateway, CLI, x402, Skills (5/5) |
| Public GitHub repo | github.com/4KInc/circle-prize-submission |
| Real USDC transaction | 3 mainnet txs on Basescan (links above) |
| Agent wallet addresses | Customer, Treasury, Validator (all linked) |
| Agent-driven, not human checkout | Background scheduler executes autonomously every 30 min |
```

**Files:** `README.md`

**Done when:** A judge confirms eligibility in 10 seconds from the top of the README.

---

## Priority 2: Narrative Reweight (Days 2-3)

### 2a. Lead with STEP_UP Mechanism, Not Insurance

**Problem:** The README and framing lean heavily on the insurer/carrier angle as the "why this matters" hook. But Circle's criterion for "Creativeness & Innovation" asks about "uniqueness of the use case for agentic payments." The innovation is the STEP_UP mechanism itself - an agent spending money to reduce its own decision uncertainty. Insurance is a downstream business application.

**Change:**
- Opening paragraph: lead with "an agent that spends money to make better decisions" before mentioning insurers
- The "What Is This?" section should foreground the three-state decision engine
- The insurance angle becomes "here's where the receipts go" - valuable but secondary
- Frame it: "Most agent-payment demos prove an agent *can* spend money. Verigate proves spending money can itself be a *risk-mitigation decision*."

**Files:** `README.md`

### 2b. Innovation Framing for DevPost

The DevPost text description should mirror the README's STEP_UP-first narrative. Key sentence for the innovation section:

"Verigate introduces a three-state authorization model where uncertainty triggers an autonomous economic action - the system spends a small amount of USDC to purchase external evidence before finalizing a decision. This is meaningfully different from most agent-payment demos, which only prove that an agent can spend money, not that spending money can itself be a risk-mitigation decision."

### 2c. Circle Centrality Reinforcement

The "Why Circle Is Central" section is already strong. For the video, ensure the same point is made visually: show the Circle Gateway settlement happening, show the wallet addresses on Basescan, show the x402 402 response. Don't just narrate it.

---

## Priority 3: Video Script (Days 3-4, user records)

### Structure (under 3 minutes)

| Segment | Time | Content | Why |
|---------|------|---------|-----|
| **Eligibility proof** | 0:00-0:15 | Voiceover: "Verigate uses Circle Agent Wallets, Gateway, CLI, x402, and Skills. Public repo. Three wallet addresses on Base mainnet. Every payment is agent-driven." Show: GitHub, Basescan links, dashboard. | Circle screens eligibility first |
| **The Hook** | 0:15-0:40 | Show a prompt injection attack. Without Verigate: agent transfers $50 to attacker. With Verigate: blocked instantly, denial receipt produced, $0 lost. | Emotional hook, problem statement |
| **Autonomous STEP_UP** | 0:40-1:15 | Show scheduler log or Autonomous Operations card. System clock visible. Risk engine flags uncertainty -> Treasury pays Validator $0.02 -> verdict returns -> receipt signed. **No human button visible during this sequence.** | The core innovation + TD proof |
| **Mainnet proof** | 1:15-1:30 | Open Basescan. Show real Treasury->Validator $0.02 tx. Click to show USDC movement. | Proves real, not testnet-only |
| **Operator dashboard** | 1:30-1:50 | Show the overview page: "X checks, Y blocked, $0 lost, running since Aug 9." This is what the customer (agent operator) sees. | CX criterion |
| **Circle Stack** | 1:50-2:10 | Quick visual walkthrough: wallet on Basescan, Gateway health endpoint, x402 402 response, CLI command, SKILL.md in repo. 5/5. | Centrality criterion |
| **Insurance rail** | 2:10-2:30 | Show `/v1/carrier/insureds/demo/control-attestation` returning real data. "The receipt chain is designed for carrier underwriting." | Business context (secondary) |
| **Close** | 2:30-2:45 | "Verigate makes Circle the settlement layer for autonomous risk decisions." | Memorable tagline |

### Video Production Notes

- **System clock visible** during the autonomous STEP_UP sequence (proves timing)
- **No button labeled "approve," "send," or "confirm"** visible during settlement
- The Try It tab can appear briefly as a testing tool, but the autonomous scheduler flow must be the primary proof of autonomy
- Show the Autonomous Operations card prominently - it's the CX artifact
- Keep it under 3 minutes (hard requirement)

---

## Priority 4: Technical Hardening (Days 4-5)

### 4a. Proof Chain for Mainnet Transactions

**Problem:** The Basescan tx proves USDC moved. It does not prove Verigate chose it autonomously. The linked receipt and proof page bridge this gap.

**Change:** Ensure each mainnet tx ($0.05 fee, $0.02 STEP_UP) has a corresponding receipt in the proof explorer with:
- Timestamped risk evaluation preceding the transfer
- Policy trace showing which rules fired
- Intent digest binding the receipt to the specific payee/amount
- Settlement tx hash embedded in the signed receipt body

The proof explorer at `/proof/{receipt_hash}` should render this for at least one mainnet STEP_UP incident.

**Files:** `app/server.py` (proof page), stored bundles

### 4b. Validator Interoperability

**Problem:** The validator is co-deployed (same server, same operator). Judges may view this as a "simulated second opinion."

**Change:** Add `VALIDATOR_ENDPOINT` env var support so the validator can be pointed to an external service. Document that production deploys against independent validators (Blockaid, Chainlink oracle, or independent operator). The current deployment is honest: "separate service, same operator, architecturally separable."

**Files:** `circle/executor.py`, `app/server.py`, `SECURITY.md`

### 4c. Agent-Triggered Demo Path

**Problem:** The Golden Path demo requires clicking "Run Golden Path." For the video, we need a path that executes a full STEP_UP cycle programmatically.

**Change:** Add `POST /api/run/autonomous-single` that:
1. Generates a random payment intent
2. Runs risk scoring
3. If STEP_UP, executes real testnet transfers
4. Signs receipt
5. Returns the complete result

This is what the video shows: one API call, full autonomous cycle, no UI button.

**Files:** `app/server.py`

---

## Priority 5: Submission (Days 5-6)

### DevPost Form

| Field | Value |
|-------|-------|
| Category | Money & Financial Access |
| Circle prize opt-in | Yes |
| Code repo | github.com/4KInc/circle-prize-submission |
| Video | YouTube (unlisted), under 3 min |
| Revenue | $0 / $0 / $0 / $0 (honest) |
| Expenses | ~$21/month (Cloud Run $15, GCS $1, Gemini $5) |
| Users | Pre-production pipeline with 5 carriers |
| Corporate ID | BlockIntel Inc, EIN 41-4617459 |
| Pre-existing work | engine/ submodule from prior challenge, disclosed |

### Agent Marketplace

Submit the Google Form at `https://forms.gle/7YFzvdmMcn1JH5tF6` with:
- Endpoint: `/x402/security-check`
- Payout wallet: `0x0c744ecb3949b3582cdd2dbc70dc876405eec44d`
- OpenAPI: `/static/openapi.json`
- Category: `FINANCIAL_ANALYSIS`

---

## What NOT To Do

- Do **not** build full carrier OAuth (P3, quarters of work, adds little to Circle's criteria)
- Do **not** add ML to the scorer (claim says "honest statistics, not ML")
- Do **not** put Gemini in the authorization trust path
- Do **not** fabricate revenue, users, or traction
- Do **not** build the independent validator network (roadmap item)
- Do **not** spend time on the main XPRIZE criteria ($0 revenue is a hard wall there)
- Do **not** show a human clicking "approve" or "send" in the demo video

---

## Scoring Projection

| Criterion | Weight | Current | After Plan | Key Driver |
|-----------|--------|---------|------------|------------|
| Eligibility | Pass/fail | Pass (at risk on "no human checkout") | Pass (video proves autonomy) | Scheduler + video framing |
| Creativeness & Innovation | 25% | 8/10 | 9/10 | STEP_UP-first narrative |
| Centrality to Business | 25% | 9/10 | 9.5/10 | Already strong, video reinforces |
| Technical Depth & Autonomy | 25% | 9/10 | 10/10 | Scheduler with real transfers + proof chain |
| Customer Experience | 25% | 8/10 | 9/10 | Operator dashboard + video |

**Projected score: 9.4/10** - competitive for the single-winner prize.

---

## Execution Order

```
Day 1: 1d (eligibility checklist) -> 1a (operator dashboard) -> 1c (dynamic pricing)
Day 2: 1b (scheduler real transfers) -> 4c (autonomous-single endpoint)
Day 3: 2a+2b (narrative reweight) -> 4a (proof chain) -> 4b (validator interop)
Day 4: Video recording
Day 5: DevPost submission + marketplace form
Day 6: Buffer / final verification / link testing
```

The video is the single most important deliverable. Everything in Days 1-3 exists to make the video unchallengeable.
