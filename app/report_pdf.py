"""Receipt Verification PDF Report Generator.

Generates a professional, downloadable PDF containing:
- Verification results (Ed25519 signatures, hash chain, Merkle root, x401, anchor)
- Receipt chain summary with settlement bindings
- Step-by-step offline verification instructions
- Public key for independent verification
- Canonical JSON examples

Design: Navy header, dark code blocks, section accent bars — inspired by
BlockIntel Gate's carrierReceiptPdf.ts design system.
"""

from __future__ import annotations

import io
import json
import hashlib
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, Color, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable


# ── Design constants ─────────────────────────────────────────────────

NAVY = HexColor("#0f2444")
NAVY_LIGHT = HexColor("#1e3a5f")
DARK_BG = HexColor("#0d1117")
GREEN = HexColor("#16a34a")
GREEN_BG = HexColor("#dcfce7")
GREEN_BORDER = HexColor("#86efac")
RED = HexColor("#dc2626")
RED_BG = HexColor("#fee2e2")
AMBER = HexColor("#d97706")
GRAY = HexColor("#6b7280")
GRAY_LIGHT = HexColor("#f9fafb")
BORDER = HexColor("#e5e7eb")
TEXT_DARK = HexColor("#111827")
TEXT_MUTED = HexColor("#6b7280")
ACCENT = HexColor("#7c5cfc")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("VTitle", parent=ss["Title"], fontSize=20, textColor=white, alignment=TA_LEFT, leading=24),
        "subtitle": ParagraphStyle("VSub", parent=ss["Normal"], fontSize=9, textColor=HexColor("#bad2ff"), leading=12),
        "heading": ParagraphStyle("VHead", parent=ss["Heading2"], fontSize=12, textColor=NAVY, spaceBefore=4, spaceAfter=4),
        "body": ParagraphStyle("VBody", parent=ss["Normal"], fontSize=9, leading=13, textColor=TEXT_DARK),
        "small": ParagraphStyle("VSmall", parent=ss["Normal"], fontSize=7.5, textColor=TEXT_MUTED, leading=10),
        "code": ParagraphStyle("VCode", parent=ss["Normal"], fontSize=7, fontName="Courier", textColor=HexColor("#86efac"), backColor=DARK_BG, leading=10, borderPadding=6),
        "verdict_pass": ParagraphStyle("VPass", parent=ss["Normal"], fontSize=14, textColor=GREEN, backColor=GREEN_BG, borderPadding=10, alignment=TA_LEFT),
        "verdict_fail": ParagraphStyle("VFail", parent=ss["Normal"], fontSize=14, textColor=RED, backColor=RED_BG, borderPadding=10, alignment=TA_LEFT),
        "step_title": ParagraphStyle("VStep", parent=ss["Normal"], fontSize=9, textColor=NAVY, leading=12),
        "step_desc": ParagraphStyle("VStepD", parent=ss["Normal"], fontSize=8, textColor=GRAY, leading=11),
    }


def _check_icon(status: str) -> Paragraph:
    ss = getSampleStyleSheet()
    if status == "PASS":
        color, symbol = "#16a34a", "\u2713 PASS"
    elif status == "FAIL":
        color, symbol = "#dc2626", "\u2717 FAIL"
    elif status == "WARN":
        color, symbol = "#d97706", "\u26A0 WARN"
    else:
        color, symbol = "#6b7280", status
    return Paragraph(f'<font color="{color}"><b>{symbol}</b></font>',
                     ParagraphStyle("CI", parent=ss["Normal"], fontSize=9))


def _check_table(checks: list[tuple[str, str]], st: dict) -> Table:
    data = [["Check", "Result"]]
    for name, status in checks:
        data.append([name, _check_icon(status)])
    t = Table(data, colWidths=[90 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 1), (0, -1), GRAY_LIGHT),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 1), (0, -1), GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, GRAY_LIGHT]),
    ]))
    return t


def _kv_table(rows: list[tuple[str, str]], col1w=55 * mm, col2w=95 * mm) -> Table:
    data = [["Field", "Value"]]
    for k, v in rows:
        data.append([k, v])
    t = Table(data, colWidths=[col1w, col2w])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 1), (0, -1), GRAY_LIGHT),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 1), (0, -1), GRAY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _section_bar() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=2, spaceBefore=6)


def _header_footer(canvas, doc):
    """Draw navy header and footer on every page."""
    w, h = A4
    # Header
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 22 * mm, w, 22 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawString(15 * mm, h - 14 * mm, "Verigate")
    canvas.setFont("Helvetica", 8)
    canvas.drawString(52 * mm, h - 14 * mm, "Receipt Verification Report")
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(w - 15 * mm, h - 11 * mm, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    canvas.drawRightString(w - 15 * mm, h - 16 * mm, f"Page {doc.page}")
    # Footer
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, w, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(HexColor("#bad2ff"))
    canvas.setFont("Helvetica", 6)
    canvas.drawString(15 * mm, 4 * mm, "Verigate \u00b7 Cryptographic Receipt Verification \u00b7 Circle protects the wallet. Verigate protects the operator.")
    canvas.drawRightString(w - 15 * mm, 4 * mm, "Independently verifiable  - zero trust required")
    canvas.restoreState()


def generate_verification_pdf(
    verification_state: dict,
    receipts: list[dict],
    agents: dict,
    artifacts: list[dict],
    public_key_jwk: dict | None = None,
    base_url: str = "https://your-dashboard-url",
) -> bytes:
    """Generate a PDF verification report and return bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=28 * mm, bottomMargin=16 * mm,
        leftMargin=15 * mm, rightMargin=15 * mm,
    )
    st = _styles()
    elements = []

    verification = verification_state or {}
    is_pass = verification.get("overall") == "PASS" or verification.get("status") == "PASS"

    # ── Verdict Hero ──
    verdict_text = "VERIFIED  - All cryptographic checks passed" if is_pass else "VERIFICATION INCOMPLETE"
    verdict_desc = (
        "The Ed25519 receipt chain, hash integrity, Merkle root, x401 identity binding, "
        "and wallet-signed anchor have all been verified. This receipt chain has not been tampered with."
        if is_pass else
        "Run the Golden Path demo to generate a complete receipt chain with verification."
    )
    v_color = GREEN if is_pass else RED
    v_bg = GREEN_BG if is_pass else RED_BG
    v_border = HexColor("#86efac") if is_pass else HexColor("#fca5a5")
    hero_title = Paragraph(f'<font color="{v_color.hexval()}"><b>{verdict_text}</b></font>',
                           ParagraphStyle("VHT", parent=st["body"], fontSize=14, leading=18))
    hero_desc = Paragraph(verdict_desc,
                          ParagraphStyle("VHD", parent=st["body"], fontSize=9, leading=13, spaceBefore=4))
    hero_table = Table([[hero_title], [hero_desc]], colWidths=[170 * mm])
    hero_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), v_bg),
        ("BOX", (0, 0), (-1, -1), 1, v_border),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    elements.append(hero_table)
    elements.append(Spacer(1, 4 * mm))

    # ── Verification Checks ──
    elements.append(_section_bar())
    elements.append(Paragraph('<font color="#1e3a5f"><b>VERIFICATION CHECKS</b></font>', st["heading"]))

    checks = []
    for key, label in [
        ("signatures", "Ed25519 Signatures"),
        ("hash_chain", "Hash Chain Integrity"),
        ("merkle", "Merkle Root (RFC 6962)"),
        ("x401", "x401 Identity Binding"),
        ("anchor", "Wallet-Signed Anchor"),
        ("overall", "Overall Verdict"),
    ]:
        val = verification.get(key, "NOT RUN")
        checks.append((label, val))
    elements.append(_check_table(checks, st))
    elements.append(Spacer(1, 4 * mm))

    # ── Receipt Chain Summary ──
    elements.append(_section_bar())
    elements.append(Paragraph('<font color="#1e3a5f"><b>RECEIPT CHAIN SUMMARY</b></font>', st["heading"]))

    n_receipts = len(receipts)
    approvals = sum(1 for r in receipts if r.get("body", {}).get("decision") == "approve")
    denials = sum(1 for r in receipts if r.get("body", {}).get("decision") == "deny")
    x401_bound = sum(
        1 for r in receipts
        if r.get("body", {}).get("delegation_context", {}).get("x401_credential_hash")
    )
    settlements = [
        r for r in receipts
        if r.get("body", {}).get("delegation_context", {}).get("settlement_tx")
    ]

    elements.append(_kv_table([
        ("Total Receipts", str(n_receipts)),
        ("Payments Approved", str(approvals)),
        ("Payments Denied", str(denials)),
        ("x401 Identity Bindings", str(x401_bound)),
        ("Settlement Bindings", str(len(settlements))),
        ("Signed Artifacts", str(len(artifacts))),
        ("Active Agents", str(len([a for a in agents.values() if a.get("status") == "Active"]))),
    ]))
    elements.append(Spacer(1, 4 * mm))

    # ── Settlement Details ──
    if settlements:
        elements.append(_section_bar())
        elements.append(Paragraph('<font color="#1e3a5f"><b>SETTLEMENT BINDINGS</b></font>', st["heading"]))
        elements.append(Paragraph(
            "Each approved payment receipt references the on-chain USDC settlement transaction. "
            "Neither receipt nor settlement can exist without the other (Recibo binding).",
            st["body"],
        ))
        elements.append(Spacer(1, 2 * mm))

        sdata = [["Seq", "Receipt Hash", "Tx Hash", "Amount", "Chain"]]
        for r in settlements:
            b = r.get("body", {})
            dc = b.get("delegation_context", {})
            sdata.append([
                str(b.get("seq", "?")),
                r.get("receipt_hash", "")[:32] + "...",
                dc.get("settlement_tx", "")[:24] + "...",
                str(dc.get("settlement_amount", dc.get("amount", "?"))) + " USDC",
                dc.get("settlement_chain", "?"),
            ])
        st_table = Table(sdata, colWidths=[12 * mm, 50 * mm, 42 * mm, 22 * mm, 24 * mm])
        st_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Courier"),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, GRAY_LIGHT]),
        ]))
        elements.append(st_table)
        elements.append(Spacer(1, 4 * mm))

    # ── Agent Registry ──
    elements.append(_section_bar())
    elements.append(Paragraph('<font color="#1e3a5f"><b>AGENT REGISTRY</b></font>', st["heading"]))
    elements.append(Paragraph(
        "Each agent has a unique Ed25519 signing key. All artifacts are signed independently "
        " - no agent can forge another agent's signature.",
        st["body"],
    ))
    elements.append(Spacer(1, 2 * mm))

    agent_names = {"Isolator": "Forensic Recorder"}
    adata = [["Agent", "Role", "Signing Key (kid)", "Artifacts"]]
    for name in ["Coordinator", "Gateway", "Auditor", "Investigator", "Recommender", "Isolator"]:
        ag = agents.get(name, {})
        if not ag:
            continue
        display = agent_names.get(name, name)
        adata.append([display, ag.get("role", ""), ag.get("kid", "")[:28] + "...", str(ag.get("artifacts", 0))])
    at = Table(adata, colWidths=[28 * mm, 52 * mm, 48 * mm, 18 * mm])
    at.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, GRAY_LIGHT]),
    ]))
    elements.append(at)
    elements.append(Spacer(1, 4 * mm))

    # ── Signed Artifacts ──
    if artifacts:
        elements.append(_section_bar())
        elements.append(Paragraph('<font color="#1e3a5f"><b>SIGNED ARTIFACTS</b></font>', st["heading"]))
        elements.append(Paragraph(
            "Every artifact is independently signed by its producing agent. "
            "The SHA-256 hash can be recomputed from the canonical body.",
            st["body"],
        ))
        elements.append(Spacer(1, 2 * mm))

        type_names = {"isolation_record": "forensic record"}
        agent_names_map = {"isolator": "forensic recorder"}
        art_data = [["Agent", "Type", "Artifact Hash (SHA-256)"]]
        for a in artifacts:
            agent_raw = a.get("agent", "?")
            type_raw = a.get("artifact_type", "?")
            ahash = a.get("artifact_hash", a.get("receipt_hash", ""))
            art_data.append([
                agent_names_map.get(agent_raw, agent_raw),
                type_names.get(type_raw, type_raw.replace("_", " ")),
                ahash,
            ])
        art_table = Table(art_data, colWidths=[26 * mm, 26 * mm, 128 * mm])
        art_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (2, 1), (2, -1), "Courier"),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, GRAY_LIGHT]),
        ]))
        elements.append(art_table)
        elements.append(Spacer(1, 4 * mm))

    # ── How Verification Works ──
    elements.append(_section_bar())
    elements.append(Paragraph('<font color="#1e3a5f"><b>HOW VERIFICATION WORKS</b></font>', st["heading"]))
    elements.append(Paragraph(
        "Verigate uses Ed25519 digital signatures (not HMAC)  - verification requires only the "
        "public key. No shared secrets, no trust in the operator or Circle.",
        st["body"],
    ))
    elements.append(Spacer(1, 3 * mm))

    steps = [
        ("1", "RFC 8785 JCS Canonicalization",
         "The receipt body is serialized using JSON Canonicalization Scheme (RFC 8785)  - "
         "deterministic key ordering and encoding. This ensures the exact same bytes are "
         "produced regardless of JSON library or language."),
        ("2", "SHA-256 Hash",
         "Compute SHA-256 of the canonical bytes. This becomes the receipt_hash (prefixed "
         "with 'sha256:'). Any modification to any field produces a completely different hash."),
        ("3", "Ed25519 Signature Verification",
         "The gateway signs the canonical bytes with its Ed25519 private key. Anyone with "
         "the public key can verify the signature. Ed25519 is deterministic  - the same "
         "message always produces the same signature."),
        ("4", "Hash Chain Verification",
         "Each receipt includes prev_receipt (the hash of the previous receipt). This creates "
         "an append-only chain. Inserting, deleting, or reordering receipts breaks the chain."),
        ("5", "Merkle Root + Anchor",
         "All receipt hashes are combined into an RFC 6962 Merkle tree. The root is signed "
         "by the Circle Agent Wallet and can be anchored on-chain for immutability."),
    ]
    for num, title, desc in steps:
        elements.append(KeepTogether([
            Paragraph(f'<font color="#1e3a5f"><b>Step {num}: {title}</b></font>', st["step_title"]),
            Paragraph(desc, st["step_desc"]),
            Spacer(1, 2 * mm),
        ]))
    elements.append(Spacer(1, 4 * mm))

    # ── Offline Verification Commands ──
    elements.append(_section_bar())
    elements.append(Paragraph('<font color="#1e3a5f"><b>OFFLINE VERIFICATION (no trust required)</b></font>', st["heading"]))
    elements.append(Paragraph(
        "Third-party arbiters can verify the entire receipt chain offline using only Python "
        "and the exported JSON file. No network access, no credentials, no trust in Verigate or Circle.",
        st["body"],
    ))
    elements.append(Spacer(1, 3 * mm))

    cmd_export = (
        "# Step 1: Export the chain from the dashboard\n"
        f"curl {base_url}/api/export > chain-export.json"
    )
    cmd_verify = (
        "# Step 2: Verify offline (requires only Python + cryptography)\n"
        "python -m circle.dispute verify chain-export.json"
    )
    cmd_report = (
        "# Step 3: Generate a dispute resolution PDF\n"
        "python -m circle.dispute report chain-export.json \\\n"
        "  --output dispute-report.pdf"
    )
    cmd_manual = (
        '# Manual verification with Python:\n'
        'import json, hashlib, base64\n'
        'from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey\n\n'
        '# Load export\n'
        'with open("chain-export.json") as f:\n'
        '    data = json.load(f)\n\n'
        '# Get public key (Ed25519 JWK)\n'
        'jwk = data["public_key_jwk"]\n'
        'x_bytes = base64.urlsafe_b64decode(jwk["x"] + "==")\n'
        'pub_key = Ed25519PublicKey.from_public_bytes(x_bytes)\n\n'
        '# For each receipt:\n'
        'for env in data["receipt_chain"]:\n'
        '    body_bytes = json.dumps(env["body"],\n'
        '        sort_keys=True, separators=(",",":")).encode()\n'
        '    computed = "sha256:" + hashlib.sha256(body_bytes).hexdigest()\n'
        '    assert computed == env["receipt_hash"], "TAMPERED!"\n'
        '    sig = base64.urlsafe_b64decode(env["sig"]["value"] + "==")\n'
        '    pub_key.verify(sig, body_bytes)  # raises if invalid'
    )

    for cmd in [cmd_export, cmd_verify, cmd_report]:
        elements.append(Paragraph(cmd.replace("\n", "<br/>"), st["code"]))
        elements.append(Spacer(1, 2 * mm))

    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph('<font color="#1e3a5f"><b>Manual Python Verification:</b></font>', st["step_title"]))
    elements.append(Spacer(1, 1 * mm))
    elements.append(Paragraph(cmd_manual.replace("\n", "<br/>").replace("  ", "&nbsp;&nbsp;"), st["code"]))
    elements.append(Spacer(1, 4 * mm))

    # ── Public Key ──
    if public_key_jwk:
        elements.append(_section_bar())
        elements.append(Paragraph('<font color="#1e3a5f"><b>GATEWAY PUBLIC KEY (Ed25519 JWK)</b></font>', st["heading"]))
        elements.append(Paragraph(
            "This is the gateway's Ed25519 public key in JWK format. Use it to independently "
            "verify any receipt signature. The private key never leaves the gateway process.",
            st["body"],
        ))
        elements.append(Spacer(1, 2 * mm))
        jwk_str = json.dumps(public_key_jwk, indent=2)
        elements.append(Paragraph(jwk_str.replace("\n", "<br/>").replace("  ", "&nbsp;&nbsp;"), st["code"]))
        elements.append(Spacer(1, 4 * mm))

    # ── Tamper Evidence ──
    elements.append(_section_bar())
    elements.append(Paragraph('<font color="#1e3a5f"><b>TAMPER EVIDENCE</b></font>', st["heading"]))

    tamper_style = ParagraphStyle("Tamper", parent=st["body"], fontSize=8,
                                  backColor=HexColor("#fffbeb"), borderPadding=8,
                                  textColor=HexColor("#92400e"))
    elements.append(Paragraph(
        "<b>Any modification to any receipt field</b>  - decision, amount, payee, policy hash, "
        "or timestamp  - changes the canonical JSON, producing a completely different SHA-256 hash "
        "and invalidating the Ed25519 signature. The hash chain ensures no receipt can be inserted, "
        "deleted, or reordered without detection. The Merkle root provides batch-level integrity, "
        "and the on-chain anchor makes the proof externally immutable.",
        tamper_style,
    ))
    elements.append(Spacer(1, 4 * mm))

    # ── Complementarity Note ──
    elements.append(_section_bar())
    elements.append(Paragraph('<font color="#1e3a5f"><b>RELATIONSHIP TO CIRCLE</b></font>', st["heading"]))
    elements.append(Paragraph(
        "<b>Circle protects the wallet. Verigate protects the operator.</b> "
        "Circle's Action Gate + MPC co-signer enforces spending limits at the cryptographic layer. "
        "Verigate produces the cryptographic proof that every decision was made correctly  - "
        "independently verifiable by third parties without trusting the operator or Circle. "
        "Two systems, zero overlap.",
        st["body"],
    ))
    elements.append(Spacer(1, 4 * mm))

    # ── Legal ──
    elements.append(_section_bar())
    elements.append(Paragraph(
        "<b>CERTIFICATION:</b> This report is machine-generated by Verigate and certifies that "
        "the cryptographic verification described herein was performed at the stated time. "
        "The verification result is mathematically deterministic  - identical inputs always "
        "produce identical outputs. Any party with the public key can independently replicate "
        "all verification steps without Verigate credentials.",
        st["small"],
    ))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        "<b>REGULATORY ALIGNMENT:</b> Receipt chain + signed audit reports satisfy evidence "
        "requirements under EU AI Act (Art 12-13), DORA Article 11, NIST AI RMF, and "
        "HIPAA \u00a7164.312(b). On-chain Merkle anchoring satisfies SEC Rule 17a-4(f) WORM requirements.",
        st["small"],
    ))

    # ── Build ──
    doc.build(elements, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()
