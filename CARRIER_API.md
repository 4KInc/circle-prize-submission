# Carrier API — Evidence Rail for Insurers

## Overview

Verigate produces cryptographically signed decision receipts for every
payment an AI agent screens. The Carrier API exposes these receipts to
insurance carriers for three workflows:

1. **Application / Underwriting** — carrier evaluates the insured's
   screening posture before binding coverage
2. **Renewal** — carrier reviews screening activity over the policy period
3. **Claims** — carrier retrieves the specific receipt chain for an incident

## Consent Model

The insured (agent operator) grants access:
- **Named carrier/broker** — only the designated party can retrieve
- **Time-limited** — consent expires (e.g., policy period + 90 days)
- **Purpose-bound** — underwriting, renewal, or claims
- **Tenant/agent/date-scoped** — limits to specific agents and periods
- **Revocable** — insured can revoke at any time
- **Logged** — every carrier retrieval is recorded

## Endpoints (Demo — Stubbed Auth)

These endpoints return scoped views over real receipt data under a simple
demo token. Production auth (OAuth, scoped carrier credentials) is post-prize.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/carrier/consents` | POST | Grant a carrier access (demo: accepts any token) |
| `/v1/carrier/insureds/{id}/control-attestation` | GET | Screening control attestation for the period |
| `/v1/carrier/insureds/{id}/renewal-summary` | GET | Activity summary for renewal review |
| `/v1/carrier/claims/{id}/evidence-package` | POST | Full receipt chain for a specific claim |
| `/v1/carrier/receipts/{hash}/verify` | GET | Independent receipt verification |
| `/api/carrier/evidence-bundle` | GET | Existing full evidence bundle (backward compat) |

## Control Attestation

The attestation is **data, not an audit opinion**. It states:
- Observed metrics: attempts screened, blocked, STEP_UP-escalated
- Receipt chain integrity for the period
- **Coverage caveat**: what fraction was provably routed through Verigate
- **Degraded-mode disclosure**: any period in dry-run/degraded mode
- **Reliance-scope disclaimer**: what Verigate observed, what it did not

The carrier draws the conclusion.

## What Is Stubbed (Post-Prize)

- Production OAuth-style scoped carrier credentials
- Versioned API with SLAs and per-carrier tenancy
- Carrier-friendly PDF/HTML incident reports
- Retention and revocation semantics subject to claim-retention law
- Real consent lifecycle (grant, revoke, audit log)

These will be built against a committed carrier design partner's real
requirements, not speculatively.
