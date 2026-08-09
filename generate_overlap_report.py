"""Generate Circle vs Verigate overlap analysis + pivot strategy PDF report."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime, timezone

OUTPUT = "/Users/heartlin/Projects/circle-prize-submission/circle-vs-verigate-overlap-analysis.pdf"


def build():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    # -- custom styles --
    title_style = ParagraphStyle(
        "DocTitle", parent=styles["Title"], fontSize=22,
        textColor=HexColor("#0f172a"), spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"], fontSize=11,
        textColor=HexColor("#64748b"), alignment=TA_CENTER, spaceAfter=6,
    )
    h1 = ParagraphStyle(
        "H1", parent=styles["Heading1"], fontSize=16,
        textColor=HexColor("#1e293b"), spaceBefore=14, spaceAfter=6,
    )
    h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontSize=13,
        textColor=HexColor("#334155"), spaceBefore=10, spaceAfter=4,
    )
    h3 = ParagraphStyle(
        "H3", parent=styles["Heading3"], fontSize=11,
        textColor=HexColor("#475569"), spaceBefore=8, spaceAfter=3,
    )
    body = ParagraphStyle(
        "Body2", parent=styles["Normal"], fontSize=9.5, leading=13.5,
        textColor=HexColor("#1e293b"),
    )
    body_bold = ParagraphStyle(
        "BodyBold", parent=body, fontName="Helvetica-Bold",
    )
    bullet = ParagraphStyle(
        "Bullet", parent=body, leftIndent=14, bulletIndent=4,
        spaceBefore=2, spaceAfter=2,
    )
    small = ParagraphStyle(
        "Small", parent=styles["Normal"], fontSize=8,
        textColor=HexColor("#94a3b8"), leading=10,
    )
    verdict_style = ParagraphStyle(
        "Verdict", parent=body, fontSize=10, leading=14,
        backColor=HexColor("#fef3c7"), borderPadding=6,
        textColor=HexColor("#92400e"),
    )
    verdict_green = ParagraphStyle(
        "VerdictGreen", parent=body, fontSize=10, leading=14,
        backColor=HexColor("#dcfce7"), borderPadding=6,
        textColor=HexColor("#166534"),
    )
    quote_style = ParagraphStyle(
        "Quote", parent=body, fontSize=11, leading=15,
        leftIndent=10, rightIndent=10,
        backColor=HexColor("#eff6ff"), borderPadding=8,
        textColor=HexColor("#1e40af"),
    )

    # -- table cell styles --
    tc = ParagraphStyle(
        "TableCell", parent=styles["Normal"], fontSize=7.5, leading=10,
        textColor=HexColor("#1e293b"), spaceBefore=0, spaceAfter=0,
    )
    tc_bold = ParagraphStyle(
        "TableCellBold", parent=tc, fontName="Helvetica-Bold",
    )
    tc_hdr = ParagraphStyle(
        "TableHdr", parent=tc, fontName="Helvetica-Bold", textColor=white,
    )
    tc_hdr_green = ParagraphStyle(
        "TableHdrGreen", parent=tc_hdr,
    )

    def P(text, style=tc):
        return Paragraph(text, style)
    def PH(text):
        return Paragraph(text, tc_hdr)
    def PHG(text):
        return Paragraph(text, tc_hdr_green)
    def PB(text):
        return Paragraph(text, tc_bold)

    # -- colors --
    hdr_bg = HexColor("#1e293b")
    hdr_fg = white
    row_alt = HexColor("#f8fafc")
    high_bg = HexColor("#fee2e2")
    med_bg = HexColor("#fef9c3")
    none_bg = HexColor("#dcfce7")
    grid_c = HexColor("#e2e8f0")
    PAGE_W = 174 * mm

    elements = []

    # =====================================================================
    # TITLE PAGE
    # =====================================================================
    elements.append(Spacer(1, 30 * mm))
    elements.append(Paragraph("Circle Agent Stack vs Verigate", title_style))
    elements.append(Paragraph("Overlap Analysis, Pivot Strategy &amp; Implementation", subtitle_style))
    elements.append(Spacer(1, 6 * mm))
    elements.append(HRFlowable(width="60%", thickness=1, color=HexColor("#cbd5e1")))
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(
        f"Prepared: {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
        ParagraphStyle("DateCenter", parent=small, alignment=TA_CENTER, fontSize=9),
    ))
    elements.append(Paragraph(
        "Based on: <i>The Circle Agent Stack and Agent Wallets: Architecture, "
        "Infrastructure, and the Agentic Economy</i> (detailed report, mid-2026)",
        ParagraphStyle("SrcCenter", parent=small, alignment=TA_CENTER),
    ))
    elements.append(Spacer(1, 20 * mm))
    elements.append(Paragraph(
        "This document analyzes the overlap between Circle's Agent Stack and Verigate, "
        "explains the strategic pivot from policy enforcement to cryptographic proof, "
        "and documents the new features implemented to differentiate Verigate as the "
        "missing compliance and forensics layer for Circle's ecosystem.",
        body,
    ))
    elements.append(PageBreak())

    # =====================================================================
    # 1. THE PROBLEM
    # =====================================================================
    elements.append(Paragraph("1. The Problem: Our Old Pitch Was Redundant", h1))
    elements.append(Paragraph(
        "<b>Old pitch:</b> \"Verigate stops AI agents from spending money they shouldn't.\"",
        body,
    ))
    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph(
        "A judge who reads Circle's Agent Stack report would immediately see that Circle's "
        "Action Gate + MPC co-signer already does this at the infrastructure layer. The co-signer "
        "independently refuses to sign transactions that violate spending caps, allowlists, or sanctions. "
        "Circle also has Input Guardrails (pre-LLM), Output Guardrails (post-LLM), and Firecracker "
        "microVM isolation per agent session.",
        body,
    ))
    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph(
        "Every feature we were leading with -- spending caps, allowlists, rate limits, prompt injection "
        "defense, agent isolation -- is now something Circle does natively. Positioning these as our "
        "differentiators would make us look like we don't understand Circle's stack.",
        body,
    ))
    elements.append(Spacer(1, 4 * mm))

    overlap_data = [
        [PH("Feature"), PH("Circle's Version"), PH("Verigate's Old Version"), PH("Overlap")],
        [PB("Spending caps"), P("Action Gate + MPC co-signer enforces at cryptographic layer"), P("Python PolicyEngine checks amount before CLI call"), PB("HIGH")],
        [PB("Allowlists"), P("Action Gate + MPC co-signer checks destination addresses"), P("PolicyEngine resource_scope rule"), PB("HIGH")],
        [PB("Rate limits"), P("Wallet-layer transaction volume caps via Developer Console"), P("PolicyEngine rate_limit rule"), PB("HIGH")],
        [PB("Prompt injection"), P("Input Guardrails + Action Gate + 4-layer security perimeter"), P("Zero-LLM trust path (deterministic Python)"), PB("MEDIUM")],
        [PB("Agent isolation"), P("Firecracker microVMs per session (preventive)"), P("OLD: Isolator tried to quarantine + freeze wallet (redundant)"), PB("HIGH")],
        [PB("Audit records"), P("Action Gate emits audit records (internal, not verifiable)"), P("Ed25519 signed receipt chain (independently verifiable)"), PB("LOW")],
    ]
    col_w2 = [22 * mm, 52 * mm, 52 * mm, 16 * mm]
    t2 = Table(overlap_data, colWidths=col_w2, repeatRows=1)
    t2_style = [
        ("BACKGROUND", (0, 0), (-1, 0), hdr_bg),
        ("GRID", (0, 0), (-1, -1), 0.4, grid_c),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, row in enumerate(overlap_data[1:], 1):
        level = row[3].text
        bg = high_bg if "HIGH" in level else med_bg if "MEDIUM" in level else none_bg
        t2_style.append(("BACKGROUND", (3, i), (3, i), bg))
    t2.setStyle(TableStyle(t2_style))
    elements.append(t2)

    elements.append(Spacer(1, 5 * mm))
    elements.append(Paragraph(
        "<b>Bottom line:</b> Leading with policy enforcement in the prize submission would make "
        "us look like we're competing with Circle's infrastructure -- and losing.",
        verdict_style,
    ))

    elements.append(PageBreak())

    # =====================================================================
    # 2. THE PIVOT
    # =====================================================================
    elements.append(Paragraph("2. The Pivot: From Enforcement to Proof", h1))

    elements.append(Paragraph(
        "<b>'Circle protects the wallet. Verigate protects the operator.'</b>",
        quote_style,
    ))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph(
        "The pivot reframes Verigate as <b>complementary infrastructure</b>, not a competing layer. "
        "Circle enforces spending limits at the cryptographic layer. Verigate produces cryptographic "
        "proof that every decision was made correctly -- independently verifiable by third parties "
        "without trusting the operator or Circle.",
        body,
    ))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Why this matters to a judge:", h3))
    elements.append(Spacer(1, 2 * mm))

    reasons = [
        ("<b>We stop competing with Circle and start building ON it</b> -- x401 integration, "
         "ERC-8004 reputation writes, Recibo bi-directional binding. A judge sees a team that "
         "deeply understands their stack."),
        ("<b>The receipt chain is genuinely novel</b> -- no part of Circle's 13-component stack "
         "produces Ed25519 signed, hash-chained, Merkle-anchored, independently verifiable "
         "authorization receipts with settlement binding."),
        ("<b>We solve real operator problems Circle doesn't address</b> -- regulatory compliance "
         "proof, forensic evidence for incident response, dispute resolution for third-party "
         "arbiters, policy state binding."),
        ("<b>We fill a gap the report explicitly acknowledges</b> -- Circle's report says the "
         "Action Gate 'emits an audit record for compliance monitoring' but doesn't specify the "
         "format, signing, or verifiability. That gap is Verigate's entire value proposition."),
    ]
    for r in reasons:
        elements.append(Paragraph(f"&bull; {r}", bullet))

    elements.append(PageBreak())

    # =====================================================================
    # 3. WHAT WE IMPLEMENTED
    # =====================================================================
    elements.append(Paragraph("3. What We Implemented", h1))
    elements.append(Paragraph(
        "Six new capabilities were built, each integrating with Circle's ecosystem rather than "
        "duplicating it. All are live in the dashboard and golden path demo.",
        body,
    ))
    elements.append(Spacer(1, 4 * mm))

    impl_data = [
        [PHG("Feature"), PHG("What It Does"), PHG("Relationship to Circle")],
        [
            PB("x401 Identity Binding"),
            P("Issues verifiable credentials authorizing agents with scoped permissions. "
              "Executor verifies credential signature + expiry + revocation before policy eval. "
              "Credential hash is embedded in EVERY receipt (approve and deny)."),
            P("Uses Circle's x401 standard. Binds it INTO receipts. Receipt now proves: "
              "WHO (x401) + WHAT policy + WHETHER approved + WHERE settled."),
        ],
        [
            PB("ERC-8004 Reputation"),
            P("When the Forensic Recorder documents an incident, it publishes a REAL "
              "on-chain reputation event to the deployed AgentReputation contract on "
              "Base Sepolia. Viewable on Basescan. Other operators can query the contract."),
            P("Real deployed contract at 0xf5FE7BF0...E145AA on Base Sepolia. "
              "Every reputation event is a real on-chain tx with a clickable Basescan link."),
        ],
        [
            PB("Cross-Agent Correlation"),
            P("After documenting an incident, scans all denial receipts for matching attack "
              "patterns (prompt injection, payee redirect, amount inflation, scope escape). "
              "Produces a signed correlation report: ISOLATED / SPREADING / SYSTEMIC."),
            P("Something Circle's per-session microVM isolation CANNOT do. MicroVMs prevent "
              "contamination but can't detect if multiple agents were targeted by the same attack."),
        ],
        [
            PB("Dispute Resolution"),
            P("export_chain() creates a JSON file with all receipts + public key + Merkle data. "
              "verify_export() verifies everything offline. Third-party arbiters run: "
              "python -m circle.dispute verify export.json"),
            P("Fills a gap Circle has NO answer for. Circle's audit records require trusting "
              "Circle's API. Verigate's export is self-contained cryptographic proof."),
        ],
        [
            PB("Recibo Binding"),
            P("wallet_transfer_with_recibo() embeds the receipt hash as metadata in the "
              "on-chain USDC transfer. Creates bi-directional binding: receipt references tx "
              "AND tx references receipt."),
            P("Uses Circle's Recibo smart contract. Strong demonstration of building ON "
              "Circle's stack. Neither receipt nor settlement can exist without the other."),
        ],
        [
            PB("Offline Verifier + x401 Check"),
            P("Verification pipeline now includes x401 credential binding check alongside "
              "Ed25519 signatures, hash chain, Merkle root, and anchor. All 5 checks visible "
              "in the dashboard."),
            P("Verifies that the x401 identity credential was correctly bound into each receipt. "
              "Adds a new verification dimension Circle's audit records don't have."),
        ],
    ]

    col_w3 = [26 * mm, 66 * mm, 66 * mm]
    t3 = Table(impl_data, colWidths=col_w3, repeatRows=1)
    t3_style = [
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#065f46")),
        ("GRID", (0, 0), (-1, -1), 0.4, grid_c),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(impl_data), 2):
        t3_style.append(("BACKGROUND", (0, i), (-1, i), HexColor("#f0fdf4")))
    t3.setStyle(TableStyle(t3_style))
    elements.append(t3)

    elements.append(PageBreak())

    # =====================================================================
    # 4. WHY THE PIVOT IS BENEFICIAL
    # =====================================================================
    elements.append(Paragraph("4. Why The Pivot Is Beneficial", h1))

    elements.append(Paragraph("4.1 Before vs After", h2))

    before_after = [
        [PH("Dimension"), PH("Before (Competing)"), PH("After (Complementary)")],
        [PB("Headline"), P("\"Verigate stops agents from spending money they shouldn't\""), P("\"Circle protects the wallet. Verigate protects the operator.\"")],
        [PB("Relationship to Circle"), P("Duplicates Action Gate + wallet policies at app layer"), P("Integrates with x401, ERC-8004, Recibo; fills gaps Circle doesn't address")],
        [PB("Judge perception"), P("\"Why not just use Circle's native features?\""), P("\"This makes Circle's stack enterprise-ready for regulated operators\"")],
        [PB("Key differentiator"), P("Policy engine (now table stakes)"), P("Cryptographic receipt chain (genuinely novel)")],
        [PB("Identity story"), P("Per-tenant Ed25519 keys (primitive)"), P("x401 credential binding (uses Circle's standard)")],
        [PB("Incident response"), P("Reactive quarantine + wallet freeze (overlaps with microVMs)"), P("Forensic Recorder: signed evidence + findings + recommendations for Circle's stack")],
        [PB("Verification"), P("Offline verifier (4 checks)"), P("Offline verifier (5 checks including x401) + dispute resolution CLI")],
    ]
    col_ba = [22 * mm, 62 * mm, 68 * mm]
    tba = Table(before_after, colWidths=col_ba, repeatRows=1)
    tba_style = [
        ("BACKGROUND", (0, 0), (-1, 0), hdr_bg),
        ("GRID", (0, 0), (-1, -1), 0.4, grid_c),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(before_after), 2):
        tba_style.append(("BACKGROUND", (0, i), (-1, i), row_alt))
    tba.setStyle(TableStyle(tba_style))
    elements.append(tba)

    elements.append(Spacer(1, 6 * mm))

    elements.append(Paragraph("4.2 Operator Problems Only Verigate Solves", h2))

    problems = [
        [PH("Operator Need"), PH("Circle's Answer"), PH("Verigate's Answer")],
        [P("\"Prove every payment was authorized by policy\""), P("Transaction history from Developer Console"), P("Ed25519 signed authorization receipts with policy hash binding")],
        [P("\"Show what happened when our agent got compromised\""), P("Preventive microVM isolation (no forensic evidence)"), P("Signed forensic records with findings, evidence, and recommendations + cross-agent correlation")],
        [P("\"A regulator/insurer needs to verify our agent's behavior\""), P("They'd need to trust Circle's API"), P("python -m circle.dispute verify export.json (offline, zero trust)")],
        [P("\"Which policy was active when this decision was made?\""), P("Policies are mutable via Console, no audit trail"), P("Every receipt is bound to the policy_version hash")],
        [P("\"Demonstrate EU AI Act / NIST compliance\""), P("No automated compliance reporting"), P("Gemini-powered compliance reports over real USDC spend data")],
        [P("\"Flag this agent's reputation across the ecosystem\""), P("ERC-8004 registry exists but no automated writes"), P("Real on-chain contract deployed. Forensic Recorder auto-publishes. Tx viewable on Basescan.")],
    ]
    col_prob = [38 * mm, 50 * mm, 56 * mm]
    tprob = Table(problems, colWidths=col_prob, repeatRows=1)
    tprob_style = [
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1e3a5f")),
        ("GRID", (0, 0), (-1, -1), 0.4, grid_c),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(problems), 2):
        tprob_style.append(("BACKGROUND", (0, i), (-1, i), row_alt))
    tprob.setStyle(TableStyle(tprob_style))
    elements.append(tprob)

    elements.append(PageBreak())

    # =====================================================================
    # 5. COMPLEMENTARITY MATRIX
    # =====================================================================
    elements.append(Paragraph("5. Complementarity Matrix", h1))
    elements.append(Paragraph(
        "How Verigate and Circle's Agent Stack work together at each layer. "
        "No overlap -- each system does what the other doesn't.",
        body,
    ))
    elements.append(Spacer(1, 4 * mm))

    comp_data = [
        [PH("Layer"), PH("Circle's Role"), PH("Verigate's Role")],
        [PB("Identity"), P("x401 verifiable credentials + ZK proofs"), P("Verify credential + bind hash into receipt chain")],
        [PB("Policy enforcement"), P("Action Gate + MPC co-signer (cryptographic layer)"), P("Receipt-producing layer: proves what was decided, not enforces it")],
        [PB("Settlement"), P("USDC transfer on-chain via EIP-3009"), P("Bind tx hash into signed receipt (+ Recibo reverse binding)")],
        [PB("Audit trail"), P("Internal audit records (not independently verifiable)"), P("Cryptographic receipt chain (Ed25519, hash-linked, Merkle-anchored)")],
        [PB("Incident response"), P("Preventive microVM isolation (enforcement)"), P("Forensic Recorder: signed evidence + findings + recommendations for Circle")],
        [PB("Reputation"), P("ERC-8004 registry (standard)"), P("Real deployed contract on Base Sepolia. Auto-publish forensic events on-chain.")],
        [PB("Compliance"), P("Transaction history + Developer Console"), P("Automated EU AI Act / NIST reports over real spend data")],
        [PB("Dispute resolution"), P("N/A"), P("Self-contained proof chain for third-party arbiters (offline, zero trust)")],
    ]
    col_w4 = [26 * mm, 62 * mm, 74 * mm]
    t4 = Table(comp_data, colWidths=col_w4, repeatRows=1)
    t4_style = [
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#065f46")),
        ("GRID", (0, 0), (-1, -1), 0.4, grid_c),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(comp_data), 2):
        t4_style.append(("BACKGROUND", (0, i), (-1, i), HexColor("#f0fdf4")))
    t4.setStyle(TableStyle(t4_style))
    elements.append(t4)

    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph(
        "<b>Key takeaway:</b> The old pitch made us look like we didn't understand Circle's stack. "
        "The new pitch makes us look like the missing piece that makes Circle's stack enterprise-ready "
        "for regulated operators who need <b>proof</b>, not just <b>protection</b>.",
        verdict_green,
    ))

    elements.append(PageBreak())

    # =====================================================================
    # 6. FORENSIC RECORDER REFACTOR
    # =====================================================================
    elements.append(Paragraph("6. The Forensic Recorder (formerly Isolator)", h1))
    elements.append(Paragraph(
        "The most important change in the pivot: the Isolator was <b>completely rewritten</b> "
        "as a Forensic Recorder. It no longer tries to enforce anything Circle already does.",
        body,
    ))
    elements.append(Spacer(1, 4 * mm))

    fr_data = [
        [PH("Old Isolator (Removed)"), PH("New Forensic Recorder")],
        [P("Revokes agent identity from Verigate registry"), P("Does NOT revoke — Circle's Action Gate handles identity enforcement")],
        [P("Freezes Circle wallet (calls circle wallet limit set)"), P("Does NOT freeze — Circle's wallet policies handle spending limits")],
        [P("Produces an \"isolation record\" claiming enforcement"), P("Produces a signed forensic record with findings and evidence")],
        [P("No analysis of attack vectors"), P("Analyzes attack vector: PROMPT_INJECTION_DETECTED, UNAUTHORIZED_PAYEE, AMOUNT_VIOLATION")],
        [P("No recommendations"), P("Generates actionable recommendations targeting Circle's Action Gate and wallet policies")],
        [P("Reputation publish was simulated (fake tx hash)"), P("Real on-chain contract. Every event is a Basescan-verifiable transaction.")],
    ]
    col_fr = [PAGE_W / 2, PAGE_W / 2]
    tfr = Table(fr_data, colWidths=col_fr, repeatRows=1)
    tfr_style = [
        ("BACKGROUND", (0, 0), (0, 0), high_bg),
        ("BACKGROUND", (1, 0), (1, 0), none_bg),
        ("GRID", (0, 0), (-1, -1), 0.4, grid_c),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(fr_data), 2):
        tfr_style.append(("BACKGROUND", (0, i), (-1, i), row_alt))
    tfr.setStyle(TableStyle(tfr_style))
    elements.append(tfr)

    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph("What a forensic record now contains:", h3))
    fr_fields = [
        "<b>Findings</b> — what happened, with evidence (e.g., 'PROMPT_INJECTION_DETECTED: Denial reasons contain adversarial instruction patterns')",
        "<b>Recommendations</b> — actionable items for Circle's stack (e.g., '[CIRCLE_ACTION_GATE] UPDATE_INPUT_GUARDRAILS: Review pre-LLM Input Guardrails for this attack pattern')",
        "<b>Trigger</b> — the denial receipt hash + reasons that triggered the analysis",
        "<b>Ed25519 signature</b> — independently verifiable forensic evidence",
    ]
    for f in fr_fields:
        elements.append(Paragraph(f"&bull; {f}", bullet))

    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(
        "<b>The principle:</b> We never claim to enforce. Circle's Action Gate blocks the payment. "
        "Circle's MPC co-signer refuses to sign. Circle's microVMs isolate the agent. Verigate "
        "produces the cryptographic proof of what happened, analyzes why, and recommends what "
        "Circle's stack should do next. Two systems, zero overlap.",
        verdict_green,
    ))

    elements.append(PageBreak())

    # =====================================================================
    # 7. WHAT'S LIVE IN THE DASHBOARD
    # =====================================================================
    elements.append(Paragraph("7. What's Live in the Dashboard", h1))
    elements.append(Paragraph(
        "All features are implemented and visible in the live dashboard at localhost:8080. "
        "The golden path demo now runs 16 steps (up from 14) with the new capabilities.",
        body,
    ))
    elements.append(Spacer(1, 4 * mm))

    live_data = [
        [PH("#"), PH("Pipeline Step"), PH("What the Judge Sees")],
        [P("1"), PB("Wallet Check"), P("Circle Agent Wallet funded with USDC on Base Sepolia")],
        [P("2"), PB("x401 Credential Issuance"), P("Verifiable credential issued with scoped permissions, credential hash shown")],
        [P("3"), PB("Service Discovery"), P("x402 services from Circle Marketplace + local endpoint")],
        [P("4"), PB("Gemini Ops Agent"), P("Gemini 2.5 Flash selects service and forms payment intent")],
        [P("5"), PB("Verigate Gate Init"), P("Ed25519 key + policy configured + x401 verifier attached")],
        [P("6"), PB("Authorized Payment"), P("x401 verified, policy passed, USDC settled, receipt signed with identity + tx hash")],
        [P("7"), PB("Prompt Injection"), P("Circle blocks it. Verigate produces signed denial receipt proving the attempt happened.")],
        [P("8"), PB("Forensic Recorder"), P("Signed forensic record: findings (attack vector), evidence, recommendations for Circle's Action Gate")],
        [P("9"), PB("ERC-8004 Reputation"), P("Purple card: REAL on-chain tx to deployed AgentReputation contract. Clickable Basescan link.")],
        [P("10"), PB("Cross-Agent Correlation"), P("Amber card: risk assessment (SPREADING), attack patterns, recommended actions")],
        [P("11-16"), PB("Receipts + Merkle + Verify + Compliance"), P("Receipt chain, Merkle tree, 5-check verification (incl. x401), compliance report")],
    ]
    col_live = [8 * mm, 36 * mm, PAGE_W - 44 * mm]
    tlive = Table(live_data, colWidths=col_live, repeatRows=1)
    tlive_style = [
        ("BACKGROUND", (0, 0), (-1, 0), hdr_bg),
        ("GRID", (0, 0), (-1, -1), 0.4, grid_c),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(live_data), 2):
        tlive_style.append(("BACKGROUND", (0, i), (-1, i), row_alt))
    tlive.setStyle(TableStyle(tlive_style))
    elements.append(tlive)

    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph("Verification panel now shows 5 checks:", h3))
    verify_items = [
        "Ed25519 Signatures -- PASS",
        "Hash Chain -- PASS",
        "Merkle Root -- PASS",
        "x401 Identity -- PASS (new)",
        "Anchor -- PASS",
    ]
    for v in verify_items:
        elements.append(Paragraph(f"&bull; {v}", bullet))

    elements.append(PageBreak())

    # =====================================================================
    # 8. ON-CHAIN PROOF
    # =====================================================================
    elements.append(Paragraph("8. On-Chain Proof: Deployed Contract + Real Transactions", h1))
    elements.append(Paragraph(
        "The AgentReputation contract is deployed on Base Sepolia. Every reputation "
        "event from the Forensic Recorder is a real on-chain transaction. A judge can "
        "click any tx hash and verify it on Basescan.",
        body,
    ))
    elements.append(Spacer(1, 4 * mm))

    proof_data = [
        [PH("Item"), PH("Value")],
        [PB("Contract"), P("AgentReputation (ERC-8004 compatible)")],
        [PB("Address"), P("0xf5FE7BF0163328BA0011Fa49Caf3707434E145AA")],
        [PB("Chain"), P("Base Sepolia (chain ID 84532)")],
        [PB("Deploy tx"), P("0xa80b2fe1984d947c8d85406dd44b00d691d68a6577ba7c31ae3c1b1ece606586")],
        [PB("Test event tx"), P("0x433dc13725e1d4631326bbac53dd7666d9fe0c0ff1d2accd7222b9f3d66e1695")],
        [PB("Source"), P("contracts/AgentReputation.sol (Apache-2.0)")],
        [PB("Basescan"), P("https://sepolia.basescan.org/address/0xf5FE7BF0163328BA0011Fa49Caf3707434E145AA")],
    ]
    col_proof = [26 * mm, PAGE_W - 26 * mm]
    tproof = Table(proof_data, colWidths=col_proof, repeatRows=1)
    tproof_style = [
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#065f46")),
        ("GRID", (0, 0), (-1, -1), 0.4, grid_c),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(proof_data), 2):
        tproof_style.append(("BACKGROUND", (0, i), (-1, i), row_alt))
    tproof.setStyle(TableStyle(tproof_style))
    elements.append(tproof)

    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph("Contract interface:", h3))
    interface_items = [
        "<b>recordEvent(agentId, eventType, severity, metadata)</b> — write a reputation event on-chain",
        "<b>getAgentEntryCount(agentId)</b> — query how many events exist for an agent",
        "<b>totalEntries()</b> — total events in the registry",
        "<b>ReputationRecorded</b> event — indexed by reporter and agentId for efficient querying",
    ]
    for item in interface_items:
        elements.append(Paragraph(f"&bull; {item}", bullet))

    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(
        "<b>This is not a stub.</b> Every golden path run produces a real on-chain transaction. "
        "A judge can verify it on Basescan: search the contract address, click Events, and see "
        "the ReputationRecorded logs with agent ID, severity, and forensic metadata.",
        verdict_green,
    ))

    elements.append(PageBreak())

    # =====================================================================
    # 9. IMPLEMENTATION SUMMARY
    # =====================================================================
    elements.append(Paragraph("9. Implementation Summary", h1))

    files_data = [
        [PH("File"), PH("Purpose"), PH("Lines")],
        [PB("circle/x401.py"), P("x401 credential issuance, verification, revocation -- binds agent identity into receipt chain"), P("~180")],
        [PB("circle/reputation.py"), P("ERC-8004 reputation writer -- real on-chain txs to deployed contract on Base Sepolia"), P("~130")],
        [PB("circle/correlation.py"), P("Cross-agent forensic correlation engine -- detects systemic attacks across agents"), P("~200")],
        [PB("circle/dispute.py"), P("Standalone dispute resolution verifier CLI + PDF report generator"), P("~250")],
        [PB("circle/executor.py"), P("Updated: x401 credential verification before policy eval, credential hash in all receipts"), P("modified")],
        [PB("circle/isolator.py"), P("Refactored: Forensic Recorder (no enforcement). Findings, evidence, recommendations for Circle."), P("rewritten")],
        [PB("circle/verifier.py"), P("Updated: x401 binding check added to verification pipeline"), P("modified")],
        [PB("circle/cli.py"), P("Updated: wallet_transfer_with_recibo() for bi-directional settlement binding"), P("modified")],
        [PB("circle/golden_path.py"), P("Updated: 16 steps (was 14), x401 + reputation + correlation + dispute export"), P("modified")],
        [PB("app/server.py"), P("Updated: SSE events for x401, reputation, correlation; x401 in verification state"), P("modified")],
        [PB("app/static/index.html"), P("Updated: new feed cards, verification panel, overview text, defense-in-depth diagram"), P("modified")],
        [PB("README.md"), P("Updated: repositioned around receipt chain, new comparison table, new components"), P("modified")],
    ]
    col_files = [32 * mm, 100 * mm, 16 * mm]
    tfiles = Table(files_data, colWidths=col_files, repeatRows=1)
    tfiles_style = [
        ("BACKGROUND", (0, 0), (-1, 0), hdr_bg),
        ("GRID", (0, 0), (-1, -1), 0.4, grid_c),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(2, len(files_data), 2):
        tfiles_style.append(("BACKGROUND", (0, i), (-1, i), row_alt))
    # Highlight new files in green
    for i in range(1, 5):
        tfiles_style.append(("BACKGROUND", (0, i), (-1, i), HexColor("#f0fdf4")))
    tfiles.setStyle(TableStyle(tfiles_style))
    elements.append(tfiles)

    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph(
        "All 25 existing tests continue to pass. New modules verified with integration tests. "
        "Dashboard serves all new features at localhost:8080.",
        body,
    ))

    elements.append(Spacer(1, 10 * mm))

    # Footer
    elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#cbd5e1")))
    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph(
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
        "Circle Agent Wallets Report (mid-2026) vs Verigate codebase | "
        "For $50K Circle Agentic Economy Prize submission",
        small,
    ))

    doc.build(elements)
    print(f"PDF written to: {OUTPUT}")


if __name__ == "__main__":
    build()
