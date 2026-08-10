#!/usr/bin/env python3
"""Standalone dispute resolution verifier.

This tool enables third-party arbiters (auditors, regulators, insurers,
legal teams) to verify the full Verigate authorization chain WITHOUT
trusting either the operator or Circle.

Usage:
    # Export chain from the operator
    python -m circle.dispute export --output chain-export.json

    # Verify as a third party (only needs the export file)
    python -m circle.dispute verify chain-export.json

    # Generate a dispute resolution report
    python -m circle.dispute report chain-export.json --output dispute-report.pdf

The export file contains:
- All receipt envelopes (Ed25519 signed, hash-chained)
- The gateway's public key (JWK format)
- Merkle root + inclusion proofs
- Anchor attestation data
- Isolation records (if any)
- x401 credential hashes (if bound)

The verifier needs NO network access and NO trust in the operator.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("circle.dispute")


def export_chain(
    executor,
    isolator=None,
    merkle_root: str | None = None,
    anchor_data: dict | None = None,
    public_key_anchor: dict | None = None,
    output_path: str = "/tmp/verigate-chain-export.json",
) -> str:
    """Export the full receipt chain for third-party verification.

    This is what the operator hands to an arbiter. The public key
    is wallet-signed so the verifier doesn't have to trust the operator.
    """
    chain_receipts = executor.get_receipt_chain()

    # Compute Merkle data if not provided
    if merkle_root is None and chain_receipts:
        try:
            merkle_root = executor.compute_merkle_root()
        except ValueError:
            pass

    # Compute inclusion proofs
    inclusion_proofs = {}
    for env in chain_receipts:
        rh = env["receipt_hash"]
        proof = executor.compute_inclusion_proof(rh)
        if proof:
            inclusion_proofs[rh] = proof

    export = {
        "schema": "verigate-chain-export-v0.2",
        "exported_at": datetime.now(UTC).isoformat(),
        "tenant": executor.tenant,
        "public_key_jwk": executor.get_public_key_jwk(),
        "public_key_anchor": public_key_anchor,
        "receipt_chain": chain_receipts,
        "merkle_root": merkle_root,
        "inclusion_proofs": inclusion_proofs,
        "anchor_data": anchor_data,
        "isolation_records": (
            [ir.envelope_dict() for ir in isolator.records]
            if isolator else []
        ),
        "metadata": {
            "receipt_count": len(chain_receipts),
            "has_x401_bindings": any(
                "x401_credential_hash" in env.get("body", {}).get("delegation_context", {})
                for env in chain_receipts
                if env.get("body", {}).get("delegation_context")
            ),
        },
    }

    out = Path(output_path)
    out.write_text(json.dumps(export, indent=2))
    logger.info(f"Chain exported to {out} ({len(chain_receipts)} receipts)")
    return str(out)


def verify_export(export_path: str) -> dict:
    """Verify an exported chain as a third-party arbiter.

    This function requires NO network access and NO trust in the operator.
    It uses only the public key and the receipt data in the export file.
    """
    ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "engine")
    if os.path.isdir(ENGINE_PATH) and ENGINE_PATH not in sys.path:
        sys.path.insert(0, ENGINE_PATH)

    from circle.verifier import print_report, verify_payment_chain

    with open(export_path) as f:
        export = json.load(f)

    chain_receipts = export["receipt_chain"]
    public_key_jwk = export["public_key_jwk"]
    merkle_root = export.get("merkle_root")
    inclusion_proofs = export.get("inclusion_proofs", {})
    anchor_data = export.get("anchor_data")

    report = verify_payment_chain(
        envelopes=chain_receipts,
        public_key_jwk=public_key_jwk,
        merkle_root=merkle_root,
        inclusion_proofs=inclusion_proofs,
        anchor_data=anchor_data,
    )

    print_report(report)

    # Additional dispute-specific analysis
    print(f"\n{'=' * 60}")
    print("DISPUTE RESOLUTION ANALYSIS")
    print(f"{'=' * 60}")
    print(f"  Export schema:     {export.get('schema', 'unknown')}")
    print(f"  Exported at:       {export.get('exported_at', 'unknown')}")
    print(f"  Tenant:            {export.get('tenant', 'unknown')}")
    print(f"  Receipts:          {len(chain_receipts)}")

    # Count decisions
    approvals = sum(1 for e in chain_receipts if e["body"]["decision"] == "approve")
    denials = sum(1 for e in chain_receipts if e["body"]["decision"] == "deny")
    print(f"  Approvals:         {approvals}")
    print(f"  Denials:           {denials}")

    # Check x401 bindings
    x401_bound = sum(
        1 for e in chain_receipts
        if e.get("body", {}).get("delegation_context", {}).get("x401_credential_hash")
    )
    if x401_bound:
        print(f"  x401 bindings:     {x401_bound} receipts have identity credentials bound")

    # Isolation records
    iso_records = export.get("isolation_records", [])
    if iso_records:
        print(f"  Isolation records: {len(iso_records)}")
        for ir in iso_records:
            body = ir.get("body", {})
            print(f"    - {body.get('isolation_id')}: {body.get('severity')} "
                  f"agent={body.get('agent_id')}")

    # Policy version analysis
    policy_versions = set()
    for env in chain_receipts:
        pv = env["body"].get("policy_version", "")
        if pv:
            policy_versions.add(pv)
    print(f"  Policy versions:   {len(policy_versions)} distinct")
    for pv in sorted(policy_versions):
        count = sum(1 for e in chain_receipts if e["body"].get("policy_version") == pv)
        print(f"    {pv[:30]}... ({count} receipts)")

    # Settlement binding analysis
    settlements = []
    for env in chain_receipts:
        dc = env.get("body", {}).get("delegation_context", {})
        if dc and "settlement_tx" in dc:
            settlements.append({
                "receipt_hash": env["receipt_hash"][:20] + "...",
                "tx_hash": dc["settlement_tx"][:20] + "...",
                "amount": dc.get("settlement_amount", "?"),
                "chain": dc.get("settlement_chain", "?"),
            })
    if settlements:
        print(f"\n  Settlement bindings: {len(settlements)}")
        for s in settlements:
            print(f"    Receipt {s['receipt_hash']} → tx {s['tx_hash']} "
                  f"({s['amount']} USDC on {s['chain']})")

    verdict = "VERIFIED" if report.is_green() else "VERIFICATION FAILED"
    print(f"\n  ARBITER VERDICT: {verdict}")
    print(f"{'=' * 60}")

    return {
        "verdict": verdict,
        "report": {
            "signature_check": report.signature_check,
            "chain_check": report.chain_check,
            "merkle_check": report.merkle_check,
            "x401_check": report.x401_check,
            "anchor_check": report.anchor_check,
            "overall": report.overall,
        },
        "analysis": {
            "receipts": len(chain_receipts),
            "approvals": approvals,
            "denials": denials,
            "x401_bindings": x401_bound,
            "isolation_records": len(iso_records),
            "policy_versions": len(policy_versions),
            "settlements": len(settlements),
        },
    }


def generate_dispute_report_pdf(export_path: str, output_path: str | None = None) -> str:
    """Generate a PDF dispute resolution report from an exported chain."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    result = verify_export(export_path)

    with open(export_path) as f:
        export = json.load(f)

    out = Path(output_path or "/tmp/verigate-dispute-report.pdf")
    doc = SimpleDocTemplate(str(out), pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()

    title_s = ParagraphStyle("T", parent=styles["Title"], fontSize=18, textColor=HexColor("#1a1a2a"))
    heading_s = ParagraphStyle("H", parent=styles["Heading2"], fontSize=13, textColor=HexColor("#333"))
    body_s = ParagraphStyle("B", parent=styles["Normal"], fontSize=9.5, leading=13)
    small_s = ParagraphStyle("S", parent=styles["Normal"], fontSize=8, textColor=HexColor("#888"))
    verdict_color = HexColor("#166534") if result["verdict"] == "VERIFIED" else HexColor("#991b1b")
    verdict_bg = HexColor("#dcfce7") if result["verdict"] == "VERIFIED" else HexColor("#fee2e2")

    elements = []

    elements.append(Paragraph("Verigate Dispute Resolution Report", title_s))
    elements.append(Paragraph(f"Export: {export_path}", small_s))
    elements.append(Paragraph(f"Verified: {datetime.now(UTC).isoformat()}", small_s))
    elements.append(Spacer(1, 8*mm))

    # Verdict
    elements.append(Paragraph(
        f"<b>ARBITER VERDICT: {result['verdict']}</b>",
        ParagraphStyle("V", parent=body_s, fontSize=14, textColor=verdict_color,
                       backColor=verdict_bg, borderPadding=8),
    ))
    elements.append(Spacer(1, 6*mm))

    # Verification checks
    elements.append(Paragraph("Verification Checks", heading_s))
    rpt = result["report"]
    check_data = [
        ["Check", "Result"],
        ["Ed25519 Signatures", rpt["signature_check"]],
        ["Hash Chain Integrity", rpt["chain_check"]],
        ["Merkle Root", rpt["merkle_check"]],
        ["x401 Identity Binding", rpt["x401_check"]],
        ["Anchor Attestation", rpt["anchor_check"]],
        ["Overall", rpt["overall"]],
    ]
    t = Table(check_data, colWidths=[50*mm, 30*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f0f0f0")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#ddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))

    # Analysis summary
    elements.append(Paragraph("Chain Analysis", heading_s))
    ana = result["analysis"]
    analysis_data = [
        ["Metric", "Value"],
        ["Total Receipts", str(ana["receipts"])],
        ["Payments Approved", str(ana["approvals"])],
        ["Payments Denied", str(ana["denials"])],
        ["x401 Identity Bindings", str(ana["x401_bindings"])],
        ["Isolation Records", str(ana["isolation_records"])],
        ["Distinct Policy Versions", str(ana["policy_versions"])],
        ["Settlement Bindings", str(ana["settlements"])],
    ]
    t2 = Table(analysis_data, colWidths=[50*mm, 30*mm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f0f0f0")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#ddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t2)
    elements.append(Spacer(1, 6*mm))

    # Footer
    elements.append(Paragraph(
        "This report was generated by the Verigate offline verifier. It requires no "
        "network access and no trust in either the operator or Circle. All verification "
        "is performed using the Ed25519 public key embedded in the export file and "
        "standard cryptographic operations.",
        small_s,
    ))

    doc.build(elements)
    return str(out)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Verigate Dispute Resolution Verifier")
    sub = parser.add_subparsers(dest="command")

    verify_p = sub.add_parser("verify", help="Verify an exported chain")
    verify_p.add_argument("export_file", help="Path to chain export JSON")

    report_p = sub.add_parser("report", help="Generate a dispute resolution PDF")
    report_p.add_argument("export_file", help="Path to chain export JSON")
    report_p.add_argument("--output", "-o", help="Output PDF path")

    args = parser.parse_args()

    if args.command == "verify":
        verify_export(args.export_file)
    elif args.command == "report":
        pdf = generate_dispute_report_pdf(args.export_file, args.output)
        print(f"\nDispute report written to: {pdf}")
    else:
        parser.print_help()
