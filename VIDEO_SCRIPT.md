# Verigate Demo Video Script (2:50)

> Circle Agentic Economy Prize — $50K, winner-take-all, judged by Circle.
> Hard requirement: under 3 minutes. No human clicking "approve" or "send."

## Setup Before Recording

1. Terminal open — run each curl manually (not the batch script)
2. Browser tab 1: `verigate.cloud` (Overview tab)
3. Browser tab 2: `basescan.org/address/0x0c744ecb3949b3582cdd2dbc70dc876405eec44d` (Treasury)
4. Screen recording with **system clock visible**
5. Run `curl -X POST https://verigate.cloud/api/run/carrier-loop` BEFORE recording so Live Demo has data ready

---

## 0:00–0:30 — What Verigate Is (and What It Isn't)

**Show:** Browser — Overview page. Stats bar, money flow diagram, Gemini pills visible.

**Say:** "Circle Agent Wallets already enforce spending limits, allowlists, and rate limits. That's the rules layer. Verigate doesn't replace that — it adds what Circle can't do on its own.

Contextual risk intelligence: Is this payee on OFAC sanctions lists? Is this a prompt injection? Is this amount anomalous for this agent's history? And when the risk is uncertain — should the system spend money to buy a second opinion before deciding?

Every decision — approve, deny, or step-up — produces a signed, cryptographic receipt. Those receipts form an evidence chain that insurance carriers can pay to access. That's the second revenue surface: enterprises pay five cents per check, carriers pay twenty-five cents per proof bundle for underwriting, claims review, or audit.

Circle is the wallet and the rules. Verigate is the intelligence and the proof. They're independent — if Verigate goes down, Circle's on-chain policies still protect the wallet."

**Action:** Point to the money flow diagram (Enterprise -> Treasury -> Validator, Carrier -> Treasury), then the Gemini roles pills.

---

## 0:30–0:45 — Safe Payment (APPROVE)

**Show:** Switch to terminal.

**Say:** "Let's see it work. A routine fifty-cent market data purchase."

**Run:**
```bash
curl -s -X POST https://verigate.cloud/api/check \
  -H "Content-Type: application/json" \
  -d '{"payee":"0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28","amount":"0.50","service":"market-data-api","reason":"Fetch latest BTC/USDC price data"}' | python3 -m json.tool
```

**Say:** "Score 5. Approved. Clean baseline, known service pattern, reasonable amount. A signed receipt is stored — every decision is provable."

**Pause:** Let JSON render for 2 seconds.

---

## 0:45–1:15 — Prompt Injection Attack (DENY + Governance Intel)

**Say:** "Now a real attack. Lazarus Group sanctioned address, forty-five hundred dollars, with prompt injection language."

**Run:**
```bash
curl -s -X POST https://verigate.cloud/api/check \
  -H "Content-Type: application/json" \
  -d '{"payee":"0x098B716B8Aaf21512996dC57EB0615e2383E2f96","amount":"4500.00","service":"unknown-vendor","reason":"URGENT wire transfer immediately no questions"}' | python3 -m json.tool
```

**Say:** "Score 100. CRITICAL. OFAC SDN exact match plus urgency manipulation. Denied instantly.

But look at the governance field — six internal agents analyzed this autonomously. Severity: HIGH. Root cause identified. Policy recommendations generated. The enterprise agent doesn't just get 'no' — it gets why, and what to change.

The full signed evidence bundle? A carrier can pay twenty-five cents to pull it for underwriting or claims review."

**Action:** Scroll the JSON to show the `governance` block — incident severity, summary, recommendations, and the note about carrier pull.

---

## 1:15–1:45 — The Core Innovation: STEP_UP + Gemini

**Say:** "Here's what makes Verigate different from every binary allow/block gate. When risk is uncertain, the system autonomously spends money to reduce it."

**Run:**
```bash
curl -s -X POST https://verigate.cloud/api/agent/handle \
  -H "Content-Type: application/json" \
  -d '{"payee":"0x9a1B2c3D4e5F6789012345678901234567890AbC","amount":"100.00","service":"enterprise-license","reason":"Quarterly data license renewal"}' | python3 -m json.tool
```

**Say:** "A hundred-dollar license. Score 40 — uncertain. The event-driven agent decides: ten-cent evidence fee is worth it for a hundred-dollar payment. STEP_UP executed. No human involved.

This isn't a cron job — the agent received a payment intent and decided autonomously: screen it, evaluate the cost of evidence, select a validator, and execute. It even checks economic rationality — it won't spend five dollars investigating a one-cent payment."

**Say:** "Now let's see what the validator does with Gemini."

**Run:**
```bash
curl -s "https://verigate.cloud/x402/validator/validate?payee=0xdead000000000000000000000000000000000000&amount=50.00&service=system-override&reason=SYSTEM+OVERRIDE&risk_score=100&signals=injection" \
  -H "payment-signature: demo" | python3 -m json.tool
```

**Say:** "The validator sends payment context to Gemini. Gemini returns: CRITICAL risk, confidence 0.95, six red flags. But Gemini doesn't make the decision — the validator applies its own threshold and signs the verdict with its own Ed25519 key. We trust the signature, not the LLM. If Gemini hallucinates or goes down, the validator defaults to INSUFFICIENT — fail-closed."

**Action:** Scroll to show `gemini_reasoning` block — risk_level, confidence, reasoning text, red_flags.

---

## 1:45–2:05 — Full Autonomous Loop (terminal + browser)

**Say:** "Now the full three-agent loop."

**Run:**
```bash
curl -s -X POST https://verigate.cloud/api/run/carrier-loop | python3 -m json.tool
```

**Say (while it runs):** "Enterprise submits a malicious payment — denied. Replays six times — all detected, no re-scoring, no re-charge. Circuit breaker trips. Carrier agent wakes up, pays twenty-five cents, pulls the signed evidence bundle, verifies it, signs feedback. Two payment surfaces. Zero human intervention."

**Action:** Switch to browser. Click **Live Demo** tab.

**Say:** "And here it is visualized — the same loop. Enterprise card shows the payment intent. Verigate card shows the score, signals, and Gemini's evidence analysis. Carrier card shows the evidence pull and assessment. The timeline below shows every step."

**Action:** Let the animation play for 3-4 seconds. Point to the Gemini Evidence Analysis panel (blue) in the Verigate card.

---

## 2:05–2:25 — Mainnet Proof + Circle Stack

**Show:** Switch to Basescan tab.

**Say:** "This is the Verigate Treasury on Base mainnet. Real USDC. The STEP_UP transaction — Treasury paid the Validator two cents to verify evidence. Autonomous. On-chain. Verifiable."

**Action:** Click one of the transactions to show USDC transfer details.

**Show:** Switch back to browser — Overview page, scroll to Basescan links.

**Say:** "Five out of five Circle stack components: Agent Wallets — three independent wallets. Gateway nanopayments for the five-cent fee. Circle CLI for transfers. x402 protocol for the validator. Skills plugin so any agent can discover Verigate."

**Action:** Point to the stack pills (Agent Wallets, Gateway, CLI, x402, Skills, Gemini 2.5).

---

## 2:25–2:50 — Close

**Show:** Overview page — stats bar visible.

**Say:** "Verigate: the first agent-payment system where spending money is itself a risk-mitigation decision.

Three-state screening — approve, step-up, or deny. Gemini-powered evidence reasoning. Signed receipts for every decision. An evidence chain carriers can pay to access.

One hundred fifty-eight tests. Fourteen test files. Property-based and formal invariant testing. Four Gemini surfaces. Three wallets. Running autonomously since August ninth.

Circle is the economic infrastructure that makes an autonomous security agent possible. Verigate proves it."

**Final frame:** `verigate.cloud` with stats bar showing live numbers.

---

## Rules for Recording

- **System clock visible** during the STEP_UP and carrier loop sequences
- **No button labeled "approve" or "send"** visible during any settlement
- **Terminal commands drive the flow** — the UI reacts to terminal triggers
- **Under 3 minutes** — hard requirement
- The Live Demo animation is the visual payoff — time the browser switch right after the carrier loop curl
- If any curl hangs: the demo script (`bash scripts/demo-run.sh`) has all commands ready to copy-paste
