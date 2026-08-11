# Verigate Unit Economics

## Revenue Model

| Item | Amount | When |
|------|--------|------|
| Security check fee | $0.05 USDC | Every transaction screened |
| Evidence purchase cost | $0.02 USDC | Only on STEP_UP (~20-30% of checks) |

## Break-Even Analysis

**Revenue per check:** $0.05

**Variable cost per check:**
- STEP_UP cases: $0.02 evidence purchase
- Non-STEP_UP cases: $0.00

**Break-even STEP_UP rate:** At 100% STEP_UP rate, net margin is
$0.05 - $0.02 = $0.03 per check (60% gross margin). The business is
profitable at any STEP_UP rate — the evidence cost is always less than
the fee.

**At observed STEP_UP rate (~25%):**
- Revenue per check: $0.05
- Average evidence cost: $0.02 × 0.25 = $0.005
- Net margin per check: $0.045 (90% gross margin)

## Scalable Model (Post-Hackathon)

| Tier | Fee | Target |
|------|-----|--------|
| Standard | $0.05 | Individual agents, developer testing |
| Volume | $0.02 | >1000 checks/day, API contract |
| Enterprise | Custom | Carrier-integrated, SLA-backed |

Evidence cost is a pass-through at all tiers.

## Infrastructure Cost

| Resource | Monthly Cost | Notes |
|----------|-------------|-------|
| Cloud Run (1 min-instance) | ~$15 | Always-on for scheduler |
| GCS proof bundles | ~$1 | <100MB/month |
| Gemini API (compliance) | ~$5 | ~50 reports/month |
| Circle CLI / wallets | $0 | Free on testnet |
| **Total** | **~$21/month** | |

## Metrics (Computed from Real Data)

These are surfaced on the dashboard Autonomous Operations card
and computed from actual scheduler runs and demo executions, not
hardcoded.

- `total_runs`: number of autonomous risk checks completed
- `total_approved`: checks resulting in APPROVE
- `total_step_up`: checks resulting in STEP_UP
- `total_denied`: checks resulting in DENY
- `step_up_rate`: total_step_up / total_runs

The scheduler runs risk-scoring-only (no real USDC transfers).
Real USDC flows are demonstrated via the mainnet STEP_UP transactions
and the Golden Path demo.
