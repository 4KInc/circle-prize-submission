# Verigate Unit Economics

## Two Products, Two Payers

Verigate has two distinct revenue surfaces, each paid by the party that
receives the value. This is not a single product with two fees — it is
two products serving two different customers with different willingness
to pay.

### Product 1 — Screening (enterprise agent pays)

The enterprise agent pays **$0.05 per check** for the decision: APPROVE,
STEP_UP, or DENY. This is the top of the funnel — high-frequency,
thin-margin, volume-driven. It drives adoption and produces the evidence.

| Item | Amount | When |
|------|--------|------|
| Security check fee | $0.05 USDC | Every transaction screened |
| Evidence purchase cost | Dynamic: `max($0.02, min(amount * 0.1%, $5.00))` | Only on STEP_UP (~20-30% of checks) |

Evidence cost scales with transaction value: a $0.50 payment triggers
$0.02 evidence; a $1,000 payment triggers $1.00; a $10,000 payment
triggers $5.00 (cap).

### Product 2 — Evidence (carrier agent pays)

The carrier agent pays **$0.25 per pull** for access to the signed proof
bundle — the auditable artifact an underwriter uses for risk assessment.
This is the margin business.

| Item | Amount | Who pays | Why |
|------|--------|----------|-----|
| Evidence pull fee | $0.25 USDC | Carrier agent | Signed proof bundle access |

**Why 5× the check fee:** A decision costs $0.05; the signed evidence an
underwriter can act on costs 5× that — $0.25 — because the proof is the
product. Above a yes/no answer, still an obvious machine-scale
micropayment. Defensible range is $0.10–$0.50; $0.25 is the clean demo
value.

**Why carriers pay:** Insurers already budget for risk data; this is a
normal line item. Selling *access to evidence* is low-liability; selling
risk verdicts would be the E&O trap Verigate deliberately avoids.

### Who-Pays Map

| Component | Who pays | Amount |
|-----------|----------|--------|
| Decision + enforcement | Enterprise agent | $0.05/check |
| STEP_UP evidence purchase | Verigate treasury (pass-through) | $0.02–$5.00 |
| Signed proof bundle access | Carrier agent | $0.25/pull |

### On-Chain Payment Surfaces

Both payments settle in USDC on Base mainnet via Circle Agent Wallets:

1. **Enterprise → Verigate Treasury**: $0.05 per screening check
2. **Carrier → Verigate Treasury**: $0.25 per evidence pull (x402)

This creates a working three-party agent economy: enterprise agents,
Verigate (the neutral middle), and carrier agents — all transacting
autonomously with no human in the loop.

## Demo vs Production Pricing

The $0.25 per-pull x402 is the **demo primitive only** — clean on-chain,
a second Circle-central payment surface, and the strongest agent-to-agent
beat. Per-pull is the wrong long-run price: it incentivizes carriers to
pull less, when continuous monitoring is exactly the value.

The real model is **per-insured-per-period, tiered by depth**:

| Tier | Scope | Pricing model |
|------|-------|---------------|
| Application-time | Single pull at bind/quote | Per-pull (demo) |
| Continuous renewal | Ongoing monitoring stream | Per-insured/month |
| Claims-time | Deep evidence package | Per-incident |

This mirrors how carriers pay for any risk-data feed and matches
Verigate's existing tier structure. The actual figure is set with the
first design-partner carrier, not derived in the abstract — the demo
number's job is to make the on-chain payment legible, not to be final.

The pull fee is a config constant (`CARRIER_PULL_FEE_USDC`), not
hardcoded inline, so it's trivially retunable.

## Honest Caveat

Carrier-pays is still the **unproven core hypothesis**. Five carriers are
in evaluation; none are paying yet. The paid pull proves the *mechanism*
(an agent can pay to pull evidence), not the *market*. Frame as
"monetized rail + pipeline validating demand," never as revenue.

## Break-Even Analysis (Product 1 only)

**Revenue per check:** $0.05

**Variable cost per check:**
- STEP_UP cases: $0.02 evidence purchase
- Non-STEP_UP cases: $0.00

**At observed STEP_UP rate (~25%):**
- Revenue per check: $0.05
- Average evidence cost: $0.02 × 0.25 = $0.005
- Net margin per check: $0.045 (90% gross margin)

Product 2 (evidence pulls) is pure margin — no variable cost beyond
serving the already-stored proof bundle.

## Scalable Model

| Tier | Check Fee | Pull Fee | Target |
|------|-----------|----------|--------|
| Standard | $0.05 | $0.25/pull | Individual agents, dev testing |
| Volume | $0.02 | $0.25/pull | >1000 checks/day, API contract |
| Enterprise | Custom | Per-insured/period | Carrier-integrated, SLA-backed |

## Infrastructure Cost

| Resource | Monthly Cost | Notes |
|----------|-------------|-------|
| Cloud Run (1 min-instance) | ~$15 | Always-on for scheduler |
| GCS proof bundles | ~$1 | <100MB/month |
| Gemini API (compliance) | ~$5 | ~50 reports/month |
| Circle wallets | $0 | No custody fees |
| **Total** | **~$21/month** | |

## Metrics (Computed from Real Data)

Surfaced on the dashboard Autonomous Operations card and computed from
actual scheduler runs and demo executions, not hardcoded.

- `total_runs`: number of autonomous risk checks completed
- `total_approved`: checks resulting in APPROVE
- `total_step_up`: checks resulting in STEP_UP
- `total_denied`: checks resulting in DENY
- `step_up_rate`: total_step_up / total_runs

Revenue metrics for both surfaces are available at `GET /api/carrier/audit`,
counted from real data (pulls logged, fees recorded).
