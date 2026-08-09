"""Verigate MCP Server — lets any AI agent use Verigate as a security service.

Any MCP-compatible agent (Claude, GPT, Gemini, ADK, LangChain, CrewAI)
can connect and call these tools before making a USDC payment.

Tools:
    check_payment    — Submit a payment intent for risk assessment + decision
    get_risk_score   — Quick risk check without executing
    get_receipt      — Retrieve a signed receipt
    get_evidence     — Pull the carrier evidence bundle

Run standalone:
    python -m verigate.mcp_server

Or use with Claude Desktop / any MCP client:
    Add to claude_desktop_config.json:
    {
      "mcpServers": {
        "verigate": {
          "command": "python",
          "args": ["-m", "verigate.mcp_server"]
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
import os

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("verigate.mcp")

mcp = FastMCP(
    "Verigate",
    instructions=(
        "Verigate is an autonomous transaction-security agent. "
        "AI agents call these tools to check if a USDC payment is safe "
        "before executing it. Verigate scores risk, buys independent "
        "evidence when uncertain, and returns a signed receipt."
    ),
)


@mcp.tool()
def check_payment(
    payee: str,
    amount: str,
    service: str,
    reason: str,
    chain: str = "BASE-SEPOLIA",
) -> dict:
    """Check if a USDC payment is safe before executing it.

    Runs deterministic policy checks and BlockIntel risk scoring.
    Returns one of three decisions:
      - APPROVE: payment is safe
      - STEP_UP: uncertain, Verigate will buy independent evidence first
      - DENY: payment is blocked

    Args:
        payee: Destination wallet address (0x...)
        amount: USDC amount as string (e.g. "0.01")
        service: Name of the service being paid for
        reason: Why the agent wants to make this payment
        chain: Blockchain network (default: BASE-SEPOLIA)

    Returns:
        Risk assessment with decision, score, confidence, signals, and receipt hash.
    """
    from circle.risk_scorer import evaluate_risk

    # Known payees from environment or defaults
    known_payees_str = os.environ.get("KNOWN_PAYEES", "")
    known_payees = [p.strip() for p in known_payees_str.split(",") if p.strip()]

    source_wallet = os.environ.get(
        "CIRCLE_AGENT_WALLET",
        "0x008ed50be2cd35f6333a37542a76a227e3b16acc",
    )

    risk = evaluate_risk(
        payee=payee,
        amount=amount,
        service=service,
        reason=reason,
        source_wallet=source_wallet,
        chain=chain,
        known_payees=known_payees or None,
    )

    return {
        "decision": risk.decision,
        "risk_score": risk.score,
        "risk_band": risk.band,
        "confidence": risk.confidence,
        "signals": risk.signals,
        "model_version": risk.model_version,
        "explanation": _explain_decision(risk),
        "thresholds": {
            "approve_ceiling": 39,
            "step_up_range": "40-74",
            "deny_floor": 75,
            "confidence_floor": 0.60,
        },
    }


@mcp.tool()
def get_risk_score(payee: str, amount: str) -> dict:
    """Quick risk score for a payee and amount. No execution, no receipt.

    Use this for a fast pre-check before calling check_payment.

    Args:
        payee: Destination wallet address
        amount: USDC amount as string

    Returns:
        Score (0-100), band (LOW/MEDIUM/HIGH/CRITICAL), and decision.
    """
    from circle.risk_scorer import evaluate_risk

    risk = evaluate_risk(
        payee=payee,
        amount=amount,
        service="quick-check",
        reason="pre-flight risk assessment",
        source_wallet="0x0000000000000000000000000000000000000000",
        chain="BASE-SEPOLIA",
    )

    return {
        "score": risk.score,
        "band": risk.band,
        "confidence": risk.confidence,
        "decision": risk.decision,
        "signals": risk.signals,
    }


@mcp.tool()
def get_receipt(receipt_hash: str) -> dict:
    """Retrieve a signed receipt by its hash.

    Receipts are cryptographic proof of payment decisions. Each contains:
    intent hash, policy result, risk assessment, settlement reference.

    Args:
        receipt_hash: The SHA-256 receipt hash (with or without sha256: prefix)

    Returns:
        The full receipt envelope if found, or an error message.
    """
    import httpx

    base_url = os.environ.get(
        "VERIGATE_API_URL",
        "https://verigate-dashboard-1031148889398.us-central1.run.app",
    )

    try:
        resp = httpx.get(f"{base_url}/api/receipts", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            receipts = data.get("receipts", [])
            for r in receipts:
                if r.get("receipt_hash", "").startswith(receipt_hash.replace("sha256:", "")):
                    return {"found": True, "receipt": r}
            return {"found": False, "message": f"No receipt matching {receipt_hash[:30]}..."}
        return {"found": False, "message": f"API returned {resp.status_code}"}
    except Exception as e:
        return {"found": False, "message": str(e)}


@mcp.tool()
def get_evidence_bundle() -> dict:
    """Pull the carrier evidence bundle.

    Returns the full audit trail for insurance underwriting and claims:
    all payments, receipts, risk scores, isolations, treasury activity,
    compliance data, and verification results.

    Returns:
        Complete evidence bundle as structured JSON.
    """
    import httpx

    base_url = os.environ.get(
        "VERIGATE_API_URL",
        "https://verigate-dashboard-1031148889398.us-central1.run.app",
    )

    try:
        resp = httpx.get(f"{base_url}/api/carrier/evidence-bundle", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"API returned {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


@mcp.resource("verigate://status")
def get_status() -> str:
    """Current Verigate system status and wallet information."""
    import httpx

    base_url = os.environ.get(
        "VERIGATE_API_URL",
        "https://verigate-dashboard-1031148889398.us-central1.run.app",
    )

    try:
        resp = httpx.get(f"{base_url}/api/wallets", timeout=10)
        if resp.status_code == 200:
            return json.dumps(resp.json(), indent=2)
    except Exception:
        pass
    return json.dumps({"status": "operational", "chain": "BASE-SEPOLIA"})


@mcp.resource("verigate://pricing")
def get_pricing() -> str:
    """Verigate pricing information."""
    return json.dumps({
        "verification_fee": "$0.05 per transaction",
        "evidence_cost": "Up to $0.01 per STEP_UP case",
        "daily_cap": "$1.00 maximum autonomous spend",
        "payment_method": "USDC via Circle Agent Wallets",
        "settlement": "Circle Gateway (sub-500ms balance access)",
    })


def _explain_decision(risk) -> str:
    """Human-readable explanation of the risk decision."""
    if risk.decision == "APPROVE":
        return (
            f"Payment looks safe. Risk score {risk.score}/100 "
            f"({risk.band}) with {risk.confidence:.0%} confidence. "
            f"Proceed with the payment."
        )
    elif risk.decision == "STEP_UP":
        signals = ", ".join(risk.signals) if risk.signals else "general uncertainty"
        return (
            f"Uncertain. Risk score {risk.score}/100 "
            f"({risk.band}), confidence {risk.confidence:.0%}. "
            f"Signals: {signals}. "
            f"Verigate will pay $0.01 for independent verification before deciding."
        )
    else:
        signals = ", ".join(risk.signals) if risk.signals else "policy violation"
        return (
            f"Blocked. Risk score {risk.score}/100 "
            f"({risk.band}) with {risk.confidence:.0%} confidence. "
            f"Signals: {signals}. "
            f"Do not proceed with this payment."
        )


def main():
    """Run the MCP server standalone."""
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
    logger.info("Starting Verigate MCP server...")
    mcp.run()


if __name__ == "__main__":
    main()
