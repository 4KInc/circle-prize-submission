"""Auditor — Gemini-powered compliance report over real USDC spend.

Generates a structured compliance report referencing:
- EU AI Act (Article 14, 15, 52) — human oversight, robustness, transparency
- NIST AI RMF (MAP, MEASURE, MANAGE, GOVERN) — risk management framework
- Actual payment data from the golden path run

The report is exportable to PDF via reportlab.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "engine")
if os.path.isdir(ENGINE_PATH) and ENGINE_PATH not in sys.path:
    sys.path.insert(0, ENGINE_PATH)

logger = logging.getLogger("circle.auditor")


def generate_compliance_report(
    payments: list[dict],
    chain_receipts: list[dict],
    isolation_records: list[dict],
    merkle_root: str,
    verification_status: str,
    wallet: str,
    chain: str,
) -> dict:
    """Generate a Gemini-powered compliance report over real USDC spend.

    Uses Gemini to analyze the payment data and produce regulatory-aware
    findings. This is the Auditor agent — one of the 6-agent system.
    """
    # Compute spend summary
    total_approved = sum(1 for p in payments if p.get("decision") == "approve")
    total_denied = sum(1 for p in payments if p.get("decision") == "deny")
    total_spend = sum(
        float(p.get("transfer", {}).get("amount", 0))
        for p in payments if p.get("decision") == "approve" and p.get("transfer")
    )
    total_isolations = len(isolation_records)

    spend_summary = {
        "total_approved": total_approved,
        "total_denied": total_denied,
        "total_spend_usdc": total_spend,
        "total_isolations": total_isolations,
        "merkle_root": merkle_root,
        "verification_status": verification_status,
        "wallet": wallet,
        "chain": chain,
    }

    # Build payment details for the prompt
    payment_details = []
    for p in payments:
        detail = {
            "decision": p.get("decision"),
            "receipt_hash": p.get("receipt_hash", "")[:32],
        }
        if p.get("transfer"):
            detail["tx_hash"] = p["transfer"].get("tx_hash", "")[:32]
            detail["amount"] = p["transfer"].get("amount")
            detail["explorer_url"] = p["transfer"].get("explorer_url")
        if p.get("denial_reasons"):
            detail["denial_reasons"] = p["denial_reasons"]
        payment_details.append(detail)

    # Try Gemini for the compliance analysis
    report = _run_gemini_audit(spend_summary, payment_details, isolation_records)
    if not report:
        report = _fallback_report(spend_summary, payment_details, isolation_records)

    return report


def _run_gemini_audit(
    spend_summary: dict,
    payment_details: list[dict],
    isolation_records: list[dict],
) -> dict | None:
    """Use Gemini to generate the compliance analysis."""
    try:
        from google import genai
    except ImportError:
        return None

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    client = genai.Client(api_key=api_key)

    prompt = f"""You are a compliance auditor for an AI agent payment system called Verigate.

Analyze the following real USDC payment data and produce a compliance report.

SPEND SUMMARY:
{json.dumps(spend_summary, indent=2)}

PAYMENT DETAILS:
{json.dumps(payment_details, indent=2)}

ISOLATION EVENTS: {len(isolation_records)} rogue agent containments

SYSTEM PROPERTIES:
- Authorization is deterministic (zero-LLM in the trust path)
- Ed25519 signed receipt chain with hash-linked integrity
- Merkle tree anchoring for tamper-evidence
- Single-use tokens (60s TTL) with JTI = Circle idempotency key
- Isolator revokes agent identity and freezes wallet on HIGH/CRITICAL violations

Produce a JSON compliance report with these sections:
{{
  "report_id": "<unique id>",
  "generated_at": "<ISO timestamp>",
  "executive_summary": "<2-3 sentence summary of findings>",
  "eu_ai_act": {{
    "article_14_human_oversight": "<finding: how the system maintains human oversight>",
    "article_15_robustness": "<finding: how the system ensures robustness and security>",
    "article_52_transparency": "<finding: how the system provides transparency>"
  }},
  "nist_ai_rmf": {{
    "govern": "<finding: governance structures in place>",
    "map": "<finding: risk identification>",
    "measure": "<finding: risk measurement and monitoring>",
    "manage": "<finding: risk mitigation and response>"
  }},
  "spend_findings": {{
    "total_governed_spend_usdc": <number>,
    "payments_approved": <number>,
    "payments_blocked": <number>,
    "rogue_agents_contained": <number>,
    "receipt_chain_integrity": "<PASS or FAIL>",
    "merkle_anchoring": "<status>"
  }},
  "recommendations": ["<list of 2-3 actionable recommendations>"]
}}

Respond ONLY with the JSON object."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Gemini audit failed: {e}")
        return None


def _fallback_report(
    spend_summary: dict,
    payment_details: list[dict],
    isolation_records: list[dict],
) -> dict:
    """Deterministic fallback when Gemini is unavailable."""
    return {
        "report_id": f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "executive_summary": (
            f"Verigate governed ${spend_summary['total_spend_usdc']:.2f} USDC in agent payments. "
            f"{spend_summary['total_approved']} payments approved, {spend_summary['total_denied']} blocked. "
            f"{spend_summary['total_isolations']} rogue agents contained. Receipt chain integrity: {spend_summary['verification_status']}."
        ),
        "eu_ai_act": {
            "article_14_human_oversight": "Deterministic policy evaluation ensures human-defined rules govern all payment decisions. No LLM in the authorization path.",
            "article_15_robustness": "Ed25519 cryptographic receipts, hash-chained integrity, and Merkle anchoring provide tamper-evidence. Isolator quarantines rogue agents.",
            "article_52_transparency": "Every decision produces a signed receipt with full audit trail. Settlement transactions are on-chain and independently verifiable.",
        },
        "nist_ai_rmf": {
            "govern": "Payment policies are defined declaratively (allowlists, caps, rate limits) and evaluated deterministically.",
            "map": "Risk identification via policy violation detection (off-allowlist payees, amount caps, rate limits).",
            "measure": "Continuous monitoring via receipt chain with real-time verification. Merkle root anchoring provides periodic checkpoints.",
            "manage": "Automated containment via Isolator (identity revocation + wallet freeze) for HIGH/CRITICAL violations.",
        },
        "spend_findings": {
            "total_governed_spend_usdc": spend_summary["total_spend_usdc"],
            "payments_approved": spend_summary["total_approved"],
            "payments_blocked": spend_summary["total_denied"],
            "rogue_agents_contained": spend_summary["total_isolations"],
            "receipt_chain_integrity": spend_summary["verification_status"],
            "merkle_anchoring": "wallet-signed attestation",
        },
        "recommendations": [
            "Enable Circle wallet spending policies on mainnet for defense-in-depth",
            "Configure per-tenant signing keys for multi-tenant isolation",
            "Schedule periodic Merkle anchoring to Base mainnet for production deployment",
        ],
    }


def export_report_pdf(report: dict, output_path: str | None = None) -> str:
    """Export the compliance report to PDF using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    out = Path(output_path or "/tmp/verigate-compliance-report.pdf")
    doc = SimpleDocTemplate(str(out), pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("Title2", parent=styles["Title"], fontSize=20, textColor=HexColor("#1a1a2a"))
    heading_style = ParagraphStyle("Heading", parent=styles["Heading2"], fontSize=14, textColor=HexColor("#333"))
    body_style = ParagraphStyle("Body2", parent=styles["Normal"], fontSize=10, leading=14)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=HexColor("#888"))

    elements = []

    # Title
    elements.append(Paragraph("Verigate Compliance Report", title_style))
    elements.append(Paragraph(f"Report ID: {report.get('report_id', 'N/A')}", small_style))
    elements.append(Paragraph(f"Generated: {report.get('generated_at', 'N/A')}", small_style))
    elements.append(Spacer(1, 10*mm))

    # Executive Summary
    elements.append(Paragraph("Executive Summary", heading_style))
    elements.append(Paragraph(report.get("executive_summary", ""), body_style))
    elements.append(Spacer(1, 6*mm))

    # Spend Findings
    elements.append(Paragraph("Spend Findings", heading_style))
    sf = report.get("spend_findings", {})
    spend_data = [
        ["Metric", "Value"],
        ["Total Governed Spend", f"${sf.get('total_governed_spend_usdc', 0):.2f} USDC"],
        ["Payments Approved", str(sf.get("payments_approved", 0))],
        ["Payments Blocked", str(sf.get("payments_blocked", 0))],
        ["Rogue Agents Contained", str(sf.get("rogue_agents_contained", 0))],
        ["Receipt Chain Integrity", str(sf.get("receipt_chain_integrity", "N/A"))],
        ["Merkle Anchoring", str(sf.get("merkle_anchoring", "N/A"))],
    ]
    t = Table(spend_data, colWidths=[55*mm, 80*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f0f0f0")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#ddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))

    # EU AI Act
    elements.append(Paragraph("EU AI Act Compliance", heading_style))
    eu = report.get("eu_ai_act", {})
    for key, label in [
        ("article_14_human_oversight", "Article 14 — Human Oversight"),
        ("article_15_robustness", "Article 15 — Robustness & Security"),
        ("article_52_transparency", "Article 52 — Transparency"),
    ]:
        elements.append(Paragraph(f"<b>{label}</b>", body_style))
        elements.append(Paragraph(eu.get(key, "N/A"), body_style))
        elements.append(Spacer(1, 3*mm))

    # NIST AI RMF
    elements.append(Paragraph("NIST AI Risk Management Framework", heading_style))
    nist = report.get("nist_ai_rmf", {})
    for key, label in [
        ("govern", "GOVERN"), ("map", "MAP"), ("measure", "MEASURE"), ("manage", "MANAGE"),
    ]:
        elements.append(Paragraph(f"<b>{label}</b>", body_style))
        elements.append(Paragraph(nist.get(key, "N/A"), body_style))
        elements.append(Spacer(1, 3*mm))

    # Recommendations
    recs = report.get("recommendations", [])
    if recs:
        elements.append(Paragraph("Recommendations", heading_style))
        for i, rec in enumerate(recs, 1):
            elements.append(Paragraph(f"{i}. {rec}", body_style))
        elements.append(Spacer(1, 6*mm))

    # Footer
    elements.append(Paragraph(
        "This report was generated by the Verigate Auditor agent using Gemini AI analysis "
        "over real USDC payment data on Base Sepolia. The authorization decisions referenced "
        "in this report are deterministic (zero-LLM) — Gemini is used only for the compliance "
        "analysis narrative, not for authorization.",
        small_style,
    ))

    doc.build(elements)
    return str(out)
