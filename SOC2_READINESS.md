# SOC 2 Readiness Assessment

> Verigate's alignment with SOC 2 Type I trust service criteria.
> This documents current controls, not a completed audit.

## Access Control (CC6)

| Control | Status | Evidence |
|---------|--------|----------|
| GCP IAM scoped per service | Implemented | Cloud Run service accounts, no shared credentials |
| Circle API keys scoped per wallet | Implemented | Customer, Treasury, Validator have independent keys |
| Ed25519 signing keys per agent | Implemented | Each of 6 governance agents has its own key pair |
| No plaintext secrets in source | Implemented | Deployer key burned from repo, env vars only |
| VALIDATOR_URL configurable | Implemented | Validators can be pointed to independent operators |

## Encryption (CC6.1)

| Control | Status | Evidence |
|---------|--------|----------|
| Encryption at rest (GCS) | Implemented | Google-managed encryption, default for GCS buckets |
| Encryption in transit (TLS) | Implemented | Cloud Run enforces TLS 1.3, HTTPS-only |
| Ed25519 receipt signatures | Implemented | Every decision signed with EdDSA, no HS256 |
| No plaintext keys in transit | Implemented | Keys generated in-memory, never serialized to disk |

## Monitoring & Logging (CC7)

| Control | Status | Evidence |
|---------|--------|----------|
| Cloud Run structured logging | Implemented | All decisions logged with severity, signals, scores |
| GCS proof bundle persistence | Implemented | Every autonomous run stored as a signed bundle |
| Receipt hash chain | Implemented | Tamper-evident linked list of all decisions |
| Merkle root anchoring | Implemented | Periodic batch roots for efficient verification |
| Scheduler uptime tracking | Implemented | `/api/scheduler/status` reports running state |

## Change Management (CC8)

| Control | Status | Evidence |
|---------|--------|----------|
| CI-enforced testing | Implemented | GitHub Actions: ruff + mypy + 158 pytest on every push |
| Property-based testing | Implemented | Hypothesis: invariants verified for arbitrary inputs |
| Formal invariant tests | Implemented | 11 named system guarantees, each with a dedicated test |
| Pre-existing work disclosed | Implemented | `engine/` submodule clearly documented in README |

## Availability (A1)

| Control | Status | Evidence |
|---------|--------|----------|
| Cloud Run min-instances=1 | Implemented | No cold-start delays for the primary service |
| GCS behavioral history persistence | Implemented | Survives Cloud Run instance recycling |
| Deterministic fallbacks for Gemini | Implemented | All Gemini calls have fail-closed conservative defaults |
| Circuit breaker on repeated denials | Implemented | Throttle at 5, suspend at 10 denials per session |

## Processing Integrity (PI1)

| Control | Status | Evidence |
|---------|--------|----------|
| Deterministic risk scorer | Implemented | Same inputs always produce same score (tested) |
| Zero LLM in authorization trust path | Implemented | Policy evaluation is Python, not Gemini |
| Fail-closed on scorer crash | Implemented | Exception propagates, never silent APPROVE |
| Replay detection (no re-charge) | Implemented | Repeated denied intents short-circuit, not re-scored |
| Settlement binding in receipts | Implemented | On-chain tx hash embedded in signed receipt body |

## Gaps & Remediation Plan

| Gap | Severity | Remediation | Timeline |
|-----|----------|-------------|----------|
| Key rotation not automated | Medium | Implement scheduled key rotation via Cloud KMS | Q4 2026 |
| No rate limit on `/api/check` | Low | Add per-IP rate limiting via Cloud Run IAM | Q4 2026 |
| Validator co-deployed (same operator) | Medium | Separate deployment with independent key material | Q4 2026 |
| No formal security audit | Medium | Engage third-party auditor for pen test + code review | Q1 2027 |

## Conclusion

Verigate meets the structural requirements for SOC 2 Type I across all five trust service criteria. The primary gaps (key rotation automation, validator independence, formal audit) are roadmap items with clear remediation paths. The system's deterministic design, CI-enforced rigor, and cryptographic receipt chain provide a strong foundation for a future Type II engagement.
