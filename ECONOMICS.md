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
hardcoded inline, so it's trivially retunable. Break-even below is
calculated using the demo per-pull model; production economics shift to
per-insured/period once design-partner carriers validate the
willingness-to-pay range.

## Monetization Gap: Governance Output

### The Problem

On every DENY, Verigate runs three governance agents (Investigator, Auditor,
Recommender) using Gemini. This costs ~$0.004 per DENY. The enterprise gets
a summary included in the $0.05 fee. The full artifacts are stored in GCS
for the carrier.

**If the carrier doesn't pull, the full artifacts sit idle and the $0.004
is wasted.**

```
Per DENY event:

  Cost to produce governance output:
    Gemini API (3 calls): ~$0.004
    GCS storage:          ~$0.0001
    Total:                ~$0.004

  Revenue:
    Enterprise summary:   $0.00  (included in $0.05 screening fee)
    Carrier pull:         $0.25  (IF carrier investigates)

  If carrier pulls:  Revenue $0.25 - Cost $0.004 = $0.246 profit
  If carrier skips:  Revenue $0.00 - Cost $0.004 = -$0.004 loss
```

The carrier self-wakes on every DENY and uses Gemini to decide whether to
investigate. It skips routine denials (blocklist hits, low-value cap
violations, repeat injection patterns) where the incremental information
value is near zero.

### The Output Flow on DENY

```
DENY event
    |
    v
Governance agents run (costs: Gemini API ~$0.004)
    |
    +-- Investigator output (forensic)
    +-- Auditor output (compliance)
    +-- Recommender output (policy proposals)
    |
    v
Split into two tiers
    |
    +-----------------------------+
    |                             |
    v                             v
Enterprise response            GCS storage
(summary, included in $0.05)  (full artifacts, stored)
    |                             |
    v                             v
$0.05 screening fee            Carrier pulls? --> YES --> $0.25
(includes summary)                |
                                  +--> NO --> sits in GCS
```

### What's Monetized vs What Sits Idle

| Output | Paid for? | By whom | If nobody pays |
|--------|-----------|---------|----------------|
| Decision (APPROVE/STEP_UP/DENY) | Always | Enterprise ($0.05) | Never unused |
| Risk score + contributions | Always | Enterprise ($0.05) | Never unused |
| Forensic **summary** | Always | Enterprise ($0.05) | Never unused |
| Recommendation **change types** | Always | Enterprise ($0.05) | Never unused |
| Forensic **full artifact** | Sometimes | Carrier ($0.25) | Sits in GCS |
| Compliance **full artifact** | Sometimes | Carrier ($0.25) | Sits in GCS |
| Recommendation **full artifact** | Sometimes | Carrier ($0.25) | Sits in GCS |

### The Fix: Governance Tier

The monetization gap is real but small (~$0.004/DENY). The governance tier
exists because the FULL forensic + recommendation output is 3-5x more
valuable than the summary, and the enterprise has demonstrated willingness
to pay for actionable intelligence.

```
Summary ($0.05): "Add to blocklist"
Full    ($0.15): "Add to blocklist because this address was used in a
                  prompt injection matching the DarkScam campaign targeting
                  procurement agents. This is the third attempt from this
                  campaign in 72 hours. Recommend also blocking the tool
                  output source and resetting the agent session."
```

The second version changes behavior. The first doesn't. That's worth $0.10.

### Three Products, Three Prices

| Product | Who pays | Fee | What they get |
|---------|----------|-----|---------------|
| Screening | Enterprise | $0.05 | Decision + risk + forensic summary + recommendation change types |
| Governance | Enterprise | $0.15 | Decision + risk + FULL forensic + FULL recommendations + signed receipt |
| Evidence | Carrier | $0.25 | Full signed proof bundle + compliance report + ERC-8004 + settlement binding |

```python
# Enterprise chooses tier at check time
response = verigate.check(
    intent=intent,
    tier="full_governance"  # $0.15 instead of $0.05
)

# Response includes full forensic + recommendations
response.governance.forensic.root_cause       # Full detail
response.governance.recommendations.changes   # Full proposals with rationale
# But NOT the compliance report — that's carrier-only
```

Every piece of intelligence Verigate produces is a product someone pays
for. No waste. No idle output.

### Alternatives Considered

**Lazy governance (run on demand):** Don't run governance agents on every
DENY — wait until someone requests the output. Problem: the enterprise
wants governance intelligence immediately, and on-demand Gemini adds
2-3 seconds of latency.

**Only run if carrier will pull:** Don't produce artifacts until the
carrier commits to $0.25. Problem: chicken-and-egg — the carrier needs to
know what's in the bundle to decide if it's worth pulling, but the bundle
doesn't exist yet.

The governance tier avoids both problems: artifacts are always produced
eagerly (for the enterprise), and the carrier can still pull the full
proof bundle independently.

## Honest Caveat

Carrier-pays is still the **unproven core hypothesis**. Five carriers are
in evaluation; none are paying yet. The paid pull proves the *mechanism*
(an agent can pay to pull evidence), not the *market*. Frame as
"monetized rail + pipeline validating demand," never as revenue.

## Break-Even Analysis (All Products)

### Product 1 Only (Screening)

**Revenue per check:** $0.05

**Variable cost per check:**
- STEP_UP cases: $0.02 evidence purchase
- Non-STEP_UP cases: $0.00

**At observed STEP_UP rate (~25%):**
- Revenue per check: $0.05
- Average evidence cost: $0.02 x 0.25 = $0.005
- Net margin per check: $0.045 (90% gross margin)

### All Three Products at Scale

```
Assumptions:
  - 10,000 checks/day
  - 25% STEP_UP rate
  - 10% DENY rate (1,000 DENYs/day)
  - 30% governance tier adoption (300 governance purchases/day)
  - 5% carrier pull rate (50 carrier pulls/day)

Daily revenue:
  Screening (Product 1):     10,000 x $0.05  = $500.00
  Governance (Product 2):       300 x $0.10  =  $30.00  (incremental over screening)
  Evidence (Product 3):          50 x $0.25  =  $12.50
  Total daily revenue:                       = $542.50

Daily variable costs:
  STEP_UP evidence:     2,500 x $0.02   =  $50.00
  Gemini (governance):  1,000 x $0.004  =   $4.00
  Gemini (carrier):        50 x $0.002  =   $0.10
  Total daily variable:                 =  $54.10

Daily gross margin: $542.50 - $54.10 = $488.40 (90% margin)
Monthly gross margin: ~$14,650
Monthly infra: ~$21
Monthly net: ~$14,629

Break-even: ~1,500 checks/day (Product 1 alone covers infra + variable)
```

Screening is the core business. Governance and evidence are margin
enhancers, not survival requirements.

## Scalable Model

| Tier | Screening | Governance | Evidence | Target |
|------|-----------|------------|----------|--------|
| Standard | $0.05 | $0.15 | $0.25/pull | Individual agents, dev testing |
| Volume | $0.02 | $0.08 | $0.25/pull | >1000 checks/day, API contract |
| Enterprise | Custom | Custom | Per-insured/period | Carrier-integrated, SLA-backed |

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
- `deny_rate`: total_denied / total_runs
- `governance_tier_adoption`: governance_purchases / total_checks
- `carrier_pull_rate`: carrier_pulls / total_denied
- `carrier_investigation_worth_rate`: investigations_started / deny_events_received
- `carrier_skip_rate`: investigations_skipped / deny_events_received

`carrier_pull_rate` is the most important — it's the conversion rate from
DENY events to carrier revenue. Revenue metrics for all three surfaces are
available at `GET /api/carrier/audit`, counted from real data (pulls logged,
fees recorded).

## Carrier Pull Rate Threshold

At what carrier pull rate does Product 3 become material?

```
Daily DENYs (at 10K checks, 10% deny rate): 1,000
Revenue per pull: $0.25

Pull rate   Pulls/day   Daily revenue   Annual revenue
---------   ---------   -------------   --------------
1%            10          $2.50           $912
5%            50          $12.50          $4,562
10%           100         $25.00          $9,125
20%           200         $50.00          $18,250
```

Screening (Product 1) is the core business. Evidence (Product 3) is a
margin enhancer that becomes material at 5%+ pull rate. The carrier
self-wake mechanism is designed to maximize pull rate by only investigating
denials with genuine insurable interest — higher quality, not higher volume.
