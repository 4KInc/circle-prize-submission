"""Single-receipt PDF generator.

Produces a one-page PDF for an individual signed receipt envelope,
suitable for download from the Receipts tab.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
)

NAVY = HexColor("#0f2444")
GREEN = HexColor("#16a34a")
RED = HexColor("#dc2626")
AMBER = HexColor("#d97706")
GRAY = HexColor("#6b7280")
GRAY_LIGHT = HexColor("#f9fafb")
BORDER = HexColor("#e5e7eb")
TEXT_DARK = HexColor("#111827")
DARK_BG = HexColor("#0d1117")


def generate_receipt_pdf(envelope: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm,
                            leftMargin=15 * mm, rightMargin=15 * mm)
    ss = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("T", parent=ss["Title"], fontSize=18, textColor=white, alignment=TA_LEFT, leading=22),
        "subtitle": ParagraphStyle("S", parent=ss["Normal"], fontSize=9, textColor=HexColor("#bad2ff"), leading=12),
        "heading": ParagraphStyle("H", parent=ss["Heading2"], fontSize=11, textColor=NAVY, spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("B", parent=ss["Normal"], fontSize=9, leading=13, textColor=TEXT_DARK),
        "small": ParagraphStyle("Sm", parent=ss["Normal"], fontSize=7.5, textColor=GRAY, leading=10),
        "code": ParagraphStyle("C", parent=ss["Normal"], fontSize=7, fontName="Courier",
                               textColor=HexColor("#86efac"), backColor=DARK_BG, leading=10, borderPadding=6),
    }

    body = envelope.get("body", {})
    sig = envelope.get("sig", {})
    receipt_hash = envelope.get("receipt_hash", "")
    decision = body.get("decision", "?")
    delegation = body.get("delegation_context", {})
    risk = delegation.get("blockintel", {})
    step_up = delegation.get("step_up", {})

    elements = []

    # Header
    header_data = [[Paragraph("Verigate — Signed Receipt", styles["title"])]]
    header = Table(header_data, colWidths=[180 * mm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 4 * mm))

    # Decision badge
    color = GREEN if decision == "approve" else RED if decision == "deny" else AMBER
    label = decision.upper()
    if step_up:
        label += " (via STEP_UP)"
    elements.append(Paragraph(f'<font color="{color.hexval()}" size="16"><b>{label}</b></font>', styles["body"]))
    elements.append(Spacer(1, 3 * mm))

    # Receipt details table
    rows = [
        ["Receipt Hash", receipt_hash],
        ["Sequence", str(body.get("seq", ""))],
        ["Timestamp", body.get("ts", "--")],
        ["Tenant", body.get("tenant", "")],
        ["Policy Version", body.get("policy_version", "")],
        ["Request Digest", body.get("request_digest", "")],
    ]
    if body.get("token_jti"):
        rows.append(["Token JTI", body["token_jti"]])
    if delegation.get("settlement_tx"):
        rows.append(["Settlement Tx", delegation["settlement_tx"]])
        rows.append(["Settlement Chain", delegation.get("settlement_chain", "")])
        rows.append(["Settlement Amount", f'{delegation.get("settlement_amount", "")} USDC'])
        rows.append(["Settlement Method", delegation.get("settlement_method", "")])
    if body.get("reasons"):
        rows.append(["Denial Reasons", ", ".join(body["reasons"])])

    t = Table(rows, colWidths=[45 * mm, 135 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Courier"),
        ("TEXTCOLOR", (0, 0), (0, -1), GRAY),
        ("TEXTCOLOR", (1, 0), (1, -1), TEXT_DARK),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (0, -1), GRAY_LIGHT),
    ]))
    elements.append(Paragraph("Receipt Details", styles["heading"]))
    elements.append(t)
    elements.append(Spacer(1, 3 * mm))

    # Risk assessment
    if risk:
        elements.append(Paragraph("BlockIntel Risk Assessment", styles["heading"]))
        risk_rows = [
            ["Risk Score", f'{risk.get("risk_score", "?")} / 100'],
            ["Risk Band", str(risk.get("risk_band", ""))],
            ["Confidence", str(risk.get("confidence", ""))],
            ["Signals", ", ".join(risk.get("signals", []))],
            ["Model", risk.get("model_version", "")],
        ]
        rt = Table(risk_rows, colWidths=[45 * mm, 135 * mm])
        rt.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (0, -1), GRAY),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("BACKGROUND", (0, 0), (0, -1), GRAY_LIGHT),
        ]))
        elements.append(rt)
        elements.append(Spacer(1, 3 * mm))

    # STEP_UP details
    if step_up:
        elements.append(Paragraph("STEP_UP Evidence Purchase", styles["heading"]))
        su_rows = [
            ["Reason", step_up.get("reason", "")],
            ["Verification Spend", f'{step_up.get("verification_spend_actual_usdc", "0")} USDC'],
            ["Validator Verdict", step_up.get("validator_verdict", "")],
        ]
        if step_up.get("verification_tx"):
            su_rows.append(["Verification Tx", step_up["verification_tx"]])
        st = Table(su_rows, colWidths=[45 * mm, 135 * mm])
        st.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Courier"),
            ("TEXTCOLOR", (0, 0), (0, -1), GRAY),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("BACKGROUND", (0, 0), (0, -1), GRAY_LIGHT),
        ]))
        elements.append(st)
        elements.append(Spacer(1, 3 * mm))

    # Ed25519 signature
    elements.append(Paragraph("Ed25519 Signature", styles["heading"]))
    sig_rows = [
        ["Algorithm", sig.get("alg", "EdDSA")],
        ["Key ID", sig.get("kid", "")],
        ["Signature", sig.get("value", "")[:80] + "..."],
    ]
    sgt = Table(sig_rows, colWidths=[45 * mm, 135 * mm])
    sgt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Courier"),
        ("TEXTCOLOR", (0, 0), (0, -1), GRAY),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (0, -1), GRAY_LIGHT),
    ]))
    elements.append(sgt)
    elements.append(Spacer(1, 4 * mm))

    # Footer
    elements.append(Paragraph(
        f'Generated by Verigate (BlockIntel Inc) at {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}. '
        f'This receipt is independently verifiable using the Ed25519 public key (kid: {sig.get("kid", "?")}).',
        styles["small"],
    ))

    doc.build(elements)
    return buf.getvalue()
