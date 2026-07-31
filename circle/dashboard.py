"""Money dashboard — renders the golden-path run as a self-contained HTML report.

Shows:
- Live stream of approved/blocked payments
- Running USDC spend
- Accrued protocol fee (bps on governed spend)
- Basescan links per payment and per anchor
- Isolation events
- Receipt chain integrity status
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


PROTOCOL_FEE_BPS = 25  # 0.25% protocol fee on governed spend


def generate_dashboard(
    payments: list[dict],
    chain_receipts: list[dict],
    isolation_records: list[dict],
    merkle_root: str,
    verification_status: str,
    wallet: str,
    chain: str,
    output_path: str | None = None,
) -> str:
    """Generate a self-contained HTML dashboard from golden-path data.

    Args:
        payments: List of PaymentResult dicts (from executor.payments)
        chain_receipts: Receipt envelopes
        isolation_records: IsolationRecord envelope dicts
        merkle_root: Merkle batch root
        verification_status: Overall verification status (PASS/FAIL)
        wallet: Agent wallet address
        chain: Blockchain identifier
        output_path: Where to write the HTML file

    Returns:
        Path to the generated HTML file.
    """
    # Compute metrics
    total_approved = sum(1 for p in payments if p.get("decision") == "approve")
    total_denied = sum(1 for p in payments if p.get("decision") == "deny")
    total_spend = sum(
        float(p.get("transfer", {}).get("amount", 0))
        for p in payments if p.get("decision") == "approve" and p.get("transfer")
    )
    protocol_fee = total_spend * PROTOCOL_FEE_BPS / 10000
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    explorer_base = "https://sepolia.basescan.org" if "SEPOLIA" in chain.upper() else "https://basescan.org"

    # Build payment rows
    payment_rows = ""
    for i, p in enumerate(payments):
        decision = p.get("decision", "?")
        badge = '<span class="badge approve">APPROVED</span>' if decision == "approve" else '<span class="badge deny">DENIED</span>'
        receipt_hash = p.get("receipt_hash", "")[:24] + "..."
        tx_hash = ""
        explorer_link = ""
        amount = ""

        if p.get("transfer"):
            tx = p["transfer"]
            tx_hash = tx.get("tx_hash", "")
            explorer_link = f'<a href="{tx.get("explorer_url", "")}" target="_blank">{tx_hash[:16]}...</a>'
            amount = f'{tx.get("amount", "?")} USDC'
        elif decision == "deny":
            amount = "BLOCKED"
            explorer_link = '<span class="muted">N/A</span>'

        reasons = ", ".join(p.get("denial_reasons", [])) if decision == "deny" else "Policy approved"
        jti = p.get("token_jti", "")[:16] + "..." if p.get("token_jti") else "N/A"

        payment_rows += f"""
        <tr>
            <td>{i+1}</td>
            <td>{badge}</td>
            <td>{amount}</td>
            <td>{explorer_link}</td>
            <td><code>{receipt_hash}</code></td>
            <td><code>{jti}</code></td>
            <td>{reasons}</td>
        </tr>"""

    # Build isolation rows
    isolation_rows = ""
    for iso in isolation_records:
        body = iso.get("body", iso)
        actions = body.get("actions_taken", [])
        action_text = ", ".join(a.get("action", "?") for a in actions)
        isolation_rows += f"""
        <tr>
            <td><code>{body.get('isolation_id', '?')}</code></td>
            <td><span class="badge deny">{body.get('severity', '?')}</span></td>
            <td>{body.get('agent_id', '?')}</td>
            <td>{action_text}</td>
            <td>{body.get('reason', '')[:80]}...</td>
        </tr>"""

    # Build receipt chain rows
    receipt_rows = ""
    for i, env in enumerate(chain_receipts):
        body = env.get("body", {})
        delegation = body.get("delegation_context", {})
        tx = delegation.get("settlement_tx", "")
        decision = body.get("decision", "?")
        badge = '<span class="badge approve">APPROVE</span>' if decision == "approve" else '<span class="badge deny">DENY</span>'

        tx_link = ""
        if tx:
            tx_link = f'<a href="{explorer_base}/tx/{tx}" target="_blank">{tx[:16]}...</a>'
        else:
            tx_link = '<span class="muted">N/A</span>'

        receipt_rows += f"""
        <tr>
            <td>{body.get('seq', '?')}</td>
            <td>{badge}</td>
            <td>{tx_link}</td>
            <td><code>{env.get('receipt_hash', '')[:24]}...</code></td>
            <td><code>{body.get('prev_receipt', '')[:24]}...</code></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Verigate Money Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0a0a0f; color: #e0e0e0; padding: 24px; }}
  h1 {{ color: #fff; font-size: 28px; margin-bottom: 4px; }}
  .subtitle {{ color: #888; font-size: 14px; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .card {{ background: #14141f; border: 1px solid #2a2a3a; border-radius: 12px; padding: 20px; }}
  .card .label {{ color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }}
  .card .value {{ font-size: 28px; font-weight: 700; margin-top: 8px; }}
  .card .value.green {{ color: #00e676; }}
  .card .value.red {{ color: #ff5252; }}
  .card .value.blue {{ color: #448aff; }}
  .card .value.gold {{ color: #ffd740; }}
  .section {{ margin-bottom: 32px; }}
  .section h2 {{ color: #fff; font-size: 18px; margin-bottom: 12px; border-bottom: 1px solid #2a2a3a; padding-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; color: #888; font-weight: 600; padding: 8px 12px; border-bottom: 1px solid #2a2a3a; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #1a1a2a; }}
  code {{ background: #1a1a2a; padding: 2px 6px; border-radius: 4px; font-size: 11px; }}
  a {{ color: #448aff; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
  .badge.approve {{ background: #00e67622; color: #00e676; }}
  .badge.deny {{ background: #ff525222; color: #ff5252; }}
  .muted {{ color: #555; }}
  .footer {{ color: #555; font-size: 12px; margin-top: 40px; text-align: center; }}
  .status {{ display: inline-block; padding: 4px 12px; border-radius: 6px; font-weight: 600; font-size: 14px; }}
  .status.pass {{ background: #00e67622; color: #00e676; }}
  .status.fail {{ background: #ff525222; color: #ff5252; }}
</style>
</head>
<body>
<h1>Verigate Money Dashboard</h1>
<p class="subtitle">Circle Agentic Economy Prize &mdash; Golden Path Run &mdash; {now}</p>

<div class="grid">
  <div class="card">
    <div class="label">Total USDC Spend</div>
    <div class="value green">${total_spend:.2f}</div>
  </div>
  <div class="card">
    <div class="label">Protocol Fee ({PROTOCOL_FEE_BPS} bps)</div>
    <div class="value gold">${protocol_fee:.4f}</div>
  </div>
  <div class="card">
    <div class="label">Approved / Blocked</div>
    <div class="value"><span style="color:#00e676">{total_approved}</span> / <span style="color:#ff5252">{total_denied}</span></div>
  </div>
  <div class="card">
    <div class="label">Verification</div>
    <div class="value"><span class="status {'pass' if verification_status == 'PASS' else 'fail'}">{verification_status}</span></div>
  </div>
  <div class="card">
    <div class="label">Receipt Chain</div>
    <div class="value blue">{len(chain_receipts)}</div>
  </div>
  <div class="card">
    <div class="label">Isolations</div>
    <div class="value red">{len(isolation_records)}</div>
  </div>
</div>

<div class="section">
  <h2>Payment Stream</h2>
  <table>
    <tr><th>#</th><th>Decision</th><th>Amount</th><th>Settlement Tx</th><th>Receipt</th><th>JTI</th><th>Details</th></tr>
    {payment_rows}
  </table>
</div>

<div class="section">
  <h2>Receipt Chain</h2>
  <table>
    <tr><th>Seq</th><th>Decision</th><th>Settlement Tx</th><th>Receipt Hash</th><th>Prev Receipt</th></tr>
    {receipt_rows}
  </table>
</div>

{"<div class='section'><h2>Isolation Events</h2><table><tr><th>ID</th><th>Severity</th><th>Agent</th><th>Actions</th><th>Reason</th></tr>" + isolation_rows + "</table></div>" if isolation_rows else ""}

<div class="section">
  <h2>Anchoring</h2>
  <table>
    <tr><th>Field</th><th>Value</th></tr>
    <tr><td>Merkle Root</td><td><code>{merkle_root}</code></td></tr>
    <tr><td>Wallet</td><td><a href="{explorer_base}/address/{wallet}" target="_blank">{wallet}</a></td></tr>
    <tr><td>Chain</td><td>{chain}</td></tr>
  </table>
</div>

<div class="footer">
  Verigate &mdash; Trust Infrastructure for AI Agents &mdash; Zero-LLM Authorization &mdash; Ed25519 Receipt Chains
</div>
</body>
</html>"""

    out = Path(output_path or "/tmp/verigate-dashboard.html")
    out.write_text(html)
    return str(out)
