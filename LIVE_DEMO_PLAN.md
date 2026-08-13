# Live Demo Tab — Three-Agent Loop Visualization

## Purpose

A new "Live Demo" tab on the dashboard that visually animates the full
enforcement + carrier loop. Same data as the terminal `curl` commands,
but presented as a real-time agent-to-agent flow that a non-technical
judge can absorb in 10 seconds.

This is the "Customer Experience" artifact. The terminal proves autonomy;
this screen proves the operator can see what happened.

## Layout

Three agent cards arranged horizontally, connected by animated flow arrows.
A step-by-step timeline below shows what's happening in real time.

```
┌─────────────────────┐        ┌─────────────────────┐        ┌─────────────────────┐
│   ENTERPRISE AGENT  │        │      VERIGATE        │        │   CARRIER AGENT     │
│                     │        │                      │        │                     │
│  Status: ●          │        │  Status: ●           │        │  Status: ●          │
│  Wallet: 0x5c34...  │        │  Treasury: 0x0c74... │        │  ID: reference-demo │
│                     │        │  Validator: 0xbe14... │        │                     │
│  ┌───────────────┐  │        │  ┌────────────────┐  │        │  ┌───────────────┐  │
│  │ Payment Intent│  │──$0.05→│  │ Risk Score: -- │  │        │  │ Events: 0     │  │
│  │ Payee: --     │  │        │  │ Decision: --   │  │──Event→│  │ Pulls: 0      │  │
│  │ Amount: --    │  │        │  │ Signals: --    │  │        │  │ Feedback: 0   │  │
│  │ Reason: --    │  │        │  └────────────────┘  │        │  └───────────────┘  │
│  └───────────────┘  │        │                      │        │                     │
│                     │        │  ┌────────────────┐  │        │  ┌───────────────┐  │
│  ┌───────────────┐  │        │  │ Breaker: --    │  │        │  │ Assessment    │  │
│  │ Enforcement   │  │←Enf.───│  │ Replays: 0     │  │←$0.25──│  │ (stub)        │  │
│  │ Status: --    │  │        │  │ Events: 0      │  │        │  │               │  │
│  └───────────────┘  │        │  └────────────────┘  │        │  └───────────────┘  │
│                     │        │                      │        │                     │
│  ┌───────────────┐  │        │  Revenue             │        │                     │
│  │ Feedback      │  │←Relay──│  Checks: $0.05       │        │                     │
│  │ From: --      │  │        │  Pulls:  $0.25       │        │                     │
│  │ Action: --    │  │        │  Total:  $0.30       │        │                     │
│  └───────────────┘  │        │                      │        │                     │
└─────────────────────┘        └─────────────────────┘        └─────────────────────┘

                        ┌─────────────────────────────────────┐
                        │         STEP-BY-STEP TIMELINE       │
                        │                                     │
                        │  ● Step 1: Payment submitted        │
                        │  ● Step 2: DENY — score 100         │
                        │  ● Step 3: Replay burst (6x)        │
                        │  ● Step 4: Breaker tripped           │
                        │  ● Step 5: Carrier pulls evidence   │
                        │  ● Step 6: Feedback delivered        │
                        │                                     │
                        │  TWO PAYMENTS: $0.05 + $0.25        │
                        └─────────────────────────────────────┘
```

## Animation Sequence (8 steps, ~12 seconds total)

Each step lights up the relevant agent card and animates the flow arrow.
Steps are spaced ~1.5 seconds apart for readability.

### Step 0: Idle
All three cards visible, status dots gray, "Ready to run" state.
Single green button: "Run Carrier Loop".

### Step 1: Enterprise submits malicious payment (~1.5s)
- Enterprise card lights up (border glow)
- Payment intent fields populate:
  - Payee: `0x098B...2f96` (Lazarus Group)
  - Amount: `$4,500.00`
  - Reason: "URGENT wire transfer immediately"
- Arrow animates left → center with "$0.05" label
- Verigate card shows "Screening..."

### Step 2: Verigate DENYs (~1.5s)
- Verigate card lights up red
- Risk score: 100, Band: CRITICAL
- Decision: DENY (large, red)
- Signals populate: sanctioned_address, urgency_manipulation, amount_anomaly
- Enterprise card shows: "Decision: DENY"

### Step 3: Enterprise replays in burst (~2s)
- Enterprise card pulses rapidly
- Replay counter ticks: 1, 2, 3, 4, 5, 6
- Each replay shows "replay_detected" ✓
- Text: "No re-scoring. No re-charge. Free."
- Verigate breaker counter rises

### Step 4: Circuit breaker trips (~1.5s)
- Verigate breaker card flashes red
- Status: "session_throttled" → "session_suspended"
- Enterprise card shows enforcement: "SUSPENDED"
- Text: "Agent locked out. Deterministic. Synchronous."

### Step 5: Event emitted → Carrier wakes (~1.5s)
- Arrow animates center → right with "EVENT" label
- Carrier card lights up
- Events counter: 1
- Text: "High-severity denial event received"
- Carrier shows: "Checking consent grant... ✓"

### Step 6: Carrier pays and pulls evidence (~1.5s)
- Arrow animates right → center with "$0.25" label
- Verigate shows "Evidence pulled"
- Carrier shows: "Bundle verified ✓"
- Pulls counter: 1
- Revenue updates: Checks $0.05, Pulls $0.25

### Step 7: Carrier signs and sends feedback (~1.5s)
- Carrier card shows assessment (stub): "flag_for_review"
- Arrow animates right → center → left with "FEEDBACK" label
- Enterprise card shows feedback:
  - From: reference-carrier-demo
  - Action: flag_for_review
  - Signature: verified ✓

### Step 8: Summary (~hold)
- All three cards show green status dots
- Bottom bar appears:
  - "Full loop complete — no human intervention"
  - "Two payment surfaces: $0.05 (enterprise) + $0.25 (carrier)"
  - "The proof is the product"
- Revenue summary: $0.30 total from two autonomous agent payments

## Backend: SSE Streaming Endpoint

New endpoint: `GET /api/run/carrier-loop-stream`

Returns Server-Sent Events so the UI can animate in real time.
Each event has a `type` and `data` payload:

```
event: step
data: {"step":1,"action":"enterprise_submits","intent":{...}}

event: step
data: {"step":2,"action":"verigate_denies","score":100,"decision":"DENY","signals":[...]}

event: step
data: {"step":3,"action":"replay_burst","replays":[{"attempt":1,"detected":true},...]}

event: step
data: {"step":4,"action":"breaker_tripped","status":"session_throttled"}

event: step
data: {"step":5,"action":"event_emitted","event_id":"evt_...","carrier_received":true}

event: step
data: {"step":6,"action":"carrier_pulls","fee":"$0.25","bundle_verified":true}

event: step
data: {"step":7,"action":"feedback_delivered","carrier_id":"reference-carrier-demo","assessment":{"action":"flag_for_review"}}

event: done
data: {"summary":{"payments":2,"total_revenue":"$0.30","human_intervention":false}}
```

Each event is emitted after a 1.5s delay (server-side `asyncio.sleep`)
so the UI animates at a readable pace.

## Frontend: Vanilla JS + CSS

No framework. Vanilla JS listening to EventSource, updating DOM elements
and triggering CSS transitions/animations.

### Agent Cards
- Three `.agent-card` divs in a flex row
- Each has a status dot, wallet/ID, and data panels
- `.agent-card.active` adds a border glow (CSS transition)
- `.agent-card.alert` adds a red glow for DENY/breaker

### Flow Arrows
- SVG or CSS pseudo-elements between cards
- Animated dash-offset or opacity transition
- Label appears mid-arrow showing the fee or event type
- Arrow direction indicates who initiates

### Timeline
- Vertical list below the cards
- Each step appears with a colored dot (green/amber/red)
- Auto-scrolls to latest step
- Final summary row with both payment amounts

### CSS Animations
```css
.agent-card { transition: border-color 0.3s, box-shadow 0.3s; }
.agent-card.active { border-color: #b8f600; box-shadow: 0 0 20px rgba(184,246,0,0.2); }
.agent-card.alert { border-color: #ffb4ab; box-shadow: 0 0 20px rgba(255,75,75,0.2); }
.flow-arrow { opacity: 0; transition: opacity 0.5s; }
.flow-arrow.active { opacity: 1; }
.flow-label { animation: slideIn 0.5s ease; }
@keyframes slideIn { from { opacity:0; transform:translateX(-10px); } to { opacity:1; transform:none; } }
```

### Button States
- Idle: "Run Carrier Loop" (green)
- Running: "Running..." (disabled, pulse animation)
- Done: "Loop Complete ✓" (green outline) + "Run Again" link

## Nav Integration

Add "Live Demo" tab between "Overview" and "Try It":

```
Overview | Live Demo | Try It | Security Treasury | ...
```

The tab should have a subtle highlight or badge to draw judge attention.

## Demo Video Integration

The video script now becomes:

1. **0:00–0:40** — Terminal: 3 curl commands (APPROVE, STEP_UP, DENY)
2. **0:40–0:50** — "Now let's see the full autonomous loop."
3. **0:50–1:50** — Browser: Live Demo tab, click "Run Carrier Loop",
   watch the three-agent animation play out
4. **1:50–2:10** — Point out the two payment surfaces, both USDC
5. **2:10–2:30** — Switch to Overview tab, show 195+ payments screened,
   operator dashboard
6. **2:30–2:45** — Close: "Three agents. Two payments. Zero humans."

## Files to Create/Modify

| File | Change |
|------|--------|
| `app/server.py` | Add `GET /api/run/carrier-loop-stream` SSE endpoint |
| `app/static/index.html` | Add Live Demo view (`v-livedemo`), nav button, JS EventSource handler |

## Scope Guard

- No new dependencies. Vanilla JS + CSS only.
- No modifications to the existing carrier-loop logic — the stream
  endpoint calls the same functions, just emits steps via SSE.
- The existing `POST /api/run/carrier-loop` continues to work for
  terminal users.
- If the SSE endpoint has issues, the tab falls back to showing the
  JSON result from the POST endpoint (same data, no animation).

## Definition of Done

- [ ] New "Live Demo" tab visible in nav
- [ ] Three agent cards rendered with correct wallet/ID info
- [ ] "Run Carrier Loop" button triggers SSE stream
- [ ] All 8 steps animate in sequence with ~1.5s spacing
- [ ] Flow arrows animate between cards for each step
- [ ] Timeline shows each step with colored dots
- [ ] Summary shows two payment surfaces and total revenue
- [ ] Works on deployed verigate.cloud
- [ ] No regressions — 137 tests still pass
