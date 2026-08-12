# Security Model

## Signing Key Custody

### Receipt Signing Keys (Ed25519)

Each Verigate instance generates a fresh Ed25519 signing key on startup.
The key ID (`kid`) is embedded in every receipt and artifact, so a verifier
can:
- Confirm which key signed a receipt
- Detect if a key has been rotated or revoked
- Verify independently using only the public key (JWK)

**Current (hackathon):** Ephemeral keys, per-instance. The public key is
anchored on-chain via wallet signature for independent verification.

**Production:** Keys loaded from GCP Secret Manager or KMS. Key rotation
generates a new `kid`; old receipts remain verifiable against the old key.
Revoked keys are published to a key-revocation list.

### ERC-8004 Deployer Key

The contract deployer key was previously hardcoded in source (testnet only,
now treated as burned). The key has been removed from source and must be
loaded from `ERC8004_DEPLOYER_KEY` environment variable. The original key
MUST NOT be reused — it was exposed in git history.

## Authorization Path (Fail-Closed)

The authorization decision is **never** served from cached, replayed, or
stale data:

- `/api/check` calls `evaluate_risk()` directly — if the scorer crashes,
  the endpoint returns HTTP 500 (fail-closed).
- Dry-run replay is for **demo display only** and is tagged with
  `dry_run_source=True` in state. It cannot produce a live authorization.
- The executor's STEP_UP path: if the validator is unreachable, the verdict
  is `UNAVAILABLE` (not silently promoted to `VERIFIED`).
- If `INSUFFICIENT_EVIDENCE` is returned by the validator, the payment is
  denied (same as `DENY`).

## Sanctions Screening

OFAC SDN screening uses exact-match only against a hand-verified static
seed of genuinely OFAC-listed Ethereum addresses. No prefix/substring
heuristics (those produce false positives). The active set's provenance
(source, publish date, content digest) is attested in every receipt via
`sanctions_feed`.

## Injection Detection

Prompt injection detection is **best-effort defense-in-depth**, not a
control. It uses structural regex patterns (role hijack, instruction
override, system prompt injection, urgency manipulation, authority
spoofing, delimiter injection) and Shannon entropy analysis.

The **hard floor** is the deterministic policy layer: OFAC screening,
amount caps, payee allowlists, and EVM address validation. These fire
independently of the injection heuristic and catch the transfer even
when the injection detection misses.

## Validator Independence

The Evidence Validator is currently a **separate service** operated by
the Verigate team on the same server. It has its own Ed25519 signing key
and wallet, but is not organizationally independent.

The validator endpoint is configurable via `VALIDATOR_URL` env var, so
the executor can be pointed to an external service (e.g., Blockaid,
Chainlink oracle, or an independent operator). The current deployment
is co-deployed but **architecturally separable**.

**Production:** Multiple external validators with independent infrastructure,
staking/reputation, and decorrelated scoring paths.
