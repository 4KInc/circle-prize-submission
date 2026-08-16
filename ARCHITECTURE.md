# Architecture Notes

## Settlement Layer Boundary

The settlement layer sits behind an interface. `circle/gateway.py` is one
implementation (Circle Gateway nanopayments on Base L2). The moat is NOT
the rail — it is:

1. **The receipt chain** — hash-linked, Ed25519 signed, Merkle-anchored
   decision proofs that are independent of any settlement rail.
2. **The carrier evidence relationships** — the consent-scoped interface
   through which insurers retrieve and verify receipts for underwriting,
   renewal, and claims.

Circle is central to the current product (5/5 stack coverage, real USDC
flows, agent wallets). But the authorization decision, the receipt, and
the carrier evidence bundle are architecturally rail-agnostic. A future
deployment on a different settlement rail would replace `gateway.py` and
`cli.py` — the receipt chain, risk scorer, and carrier interface remain
unchanged.

## Authorization Path (Fail-Closed)

```
Agent intent
    ↓
┌──────────────────────────────┐
│  evaluate_risk()             │  ← deterministic, no LLM
│  Policy + OFAC + Injection   │
│  + Amount + Payee + Service  │
│  + Behavioral (optional)     │
└──────────┬───────────────────┘
           ↓
    APPROVE / STEP_UP / DENY
           ↓
    If STEP_UP:
        Treasury → Validator $0.02
        Validator forms independent opinion
        If DENY/INSUFFICIENT → block
           ↓
    Signed receipt (Ed25519)
           ↓
    Settlement (Circle Gateway / CLI)
```

If `evaluate_risk()` crashes → HTTP 500 (fail-closed).
If validator unreachable → verdict = UNAVAILABLE.
If INSUFFICIENT_EVIDENCE → treated as DENY.
Dry-run replay → demo display only, tagged, cannot produce live auth.

## Gemini Usage

Gemini 2.5 Flash is used in **6 structural roles**:
1. STEP_UP validator reasoning (`circle/validator_gemini.py`)
2. RAG embeddings + retrieval (`circle/rag_store.py`) - Gemini embedding-001 embeds every screening decision; validator retrieves relevant history before reasoning
3. Carrier self-wake (`circle/carrier_agent.py`)
4. Governance agents (`circle/agents.py`) - Investigator, Auditor, Recommender
5. Policy synthesis (`circle/policy_synthesis.py`)
6. Cross-agent negotiation (`circle/negotiation.py`)

Gemini is **never** in the authorization trust path. The scoring
decision is deterministic Python. Gemini provides advisory input
to the validator and RAG provides historical context.

## Key Custody

- Receipt signing keys: ephemeral Ed25519, per-instance, `kid` in receipt
- ERC-8004 deployer key: env var (`ERC8004_DEPLOYER_KEY`), not in source
- Production: GCP Secret Manager / KMS
