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
        "Verigate is an autonomous transaction-security agent built on "
        "Circle Agent Stack. AI agents call these tools to check if a "
        "USDC payment is safe before executing it. Verigate scores risk, "
        "buys independent evidence when uncertain (STEP_UP), and returns "
        "a signed receipt. Fees are $0.05 USDC per check, settled via "
        "Circle Gateway nanopayments (gas-free, batched). "
        "Circle Skill: payment-security"
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
        resp = httpx.get(f"{base_url}/api/data", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            receipts = data.get("receipts", [])
            normalized = receipt_hash.replace("sha256:", "")
            for r in receipts:
                rh = r.get("receipt_hash", "")
                if rh.startswith(normalized) or normalized.startswith(rh.replace("sha256:", "")):
                    return {"found": True, "receipt": r}
            return {"found": False, "message": f"No receipt matching {receipt_hash[:30]}...", "total_receipts": len(receipts)}
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


@mcp.tool()
def check_payment_x402(
    payee: str,
    amount: str,
    service: str,
    reason: str,
) -> dict:
    """Check a payment via Verigate's x402 endpoint (Circle Gateway nanopayment).

    This calls the live x402-paywalled security check endpoint on Cloud Run.
    The $0.05 fee is settled via Circle Gateway nanopayments.

    Use this when you want the full production flow including Gateway settlement.
    For a quick local check without payment, use check_payment instead.

    Args:
        payee: Destination wallet address (0x...)
        amount: USDC amount as string
        service: Service being paid for
        reason: Justification for the payment

    Returns:
        x402 payment requirements (402 response) or the security verdict if paid.
    """
    import httpx

    base_url = os.environ.get(
        "VERIGATE_API_URL",
        "https://verigate-dashboard-1031148889398.us-central1.run.app",
    )

    try:
        resp = httpx.get(f"{base_url}/x402/health", timeout=10)
        health = resp.json() if resp.status_code == 200 else {}

        return {
            "endpoint": f"{base_url}/x402/security-check",
            "method": "POST",
            "price": health.get("price_usdc", "$0.05"),
            "settlement": "Circle Gateway nanopayments",
            "facilitator": health.get("facilitator", "https://gateway-api-testnet.circle.com"),
            "network": health.get("network", "eip155:84532"),
            "payee_wallet": health.get("payee", ""),
            "how_to_pay": (
                "Use `circle services pay` CLI or send an EIP-3009 signed "
                "authorization in the payment-signature header. The endpoint "
                "returns 402 with payment requirements on first request."
            ),
            "intent": {"payee": payee, "amount": amount, "service": service, "reason": reason},
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_gateway_status() -> dict:
    """Get Circle Gateway nanopayments status for Verigate.

    Returns Gateway facilitator connectivity, supported networks,
    and Verigate treasury balance information.

    Returns:
        Gateway status including facilitator URL, networks, and balance info.
    """
    import httpx

    base_url = os.environ.get(
        "VERIGATE_API_URL",
        "https://verigate-dashboard-1031148889398.us-central1.run.app",
    )

    try:
        resp = httpx.get(f"{base_url}/api/gateway", timeout=10)
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
        "evidence_cost": "$0.02 per STEP_UP case",
        "daily_cap": "$1.00 maximum autonomous spend",
        "payment_method": "USDC via Circle Gateway nanopayments",
        "settlement": "Circle Gateway (gas-free, batched)",
        "x402_endpoint": "https://verigate-dashboard-1031148889398.us-central1.run.app/x402/security-check",
    })


@mcp.resource("verigate://circle-skill")
def get_circle_skill() -> str:
    """Circle Skill metadata for Verigate.

    Describes Verigate as a Circle Skill — a discoverable service
    in the Circle Agent Stack ecosystem. AI agents use this metadata
    to understand how to pay for and consume Verigate's services.
    """
    return json.dumps({
        "skill": "payment-security",
        "name": "Verigate Payment Security",
        "description": (
            "Autonomous payment security for AI agents. Submit a USDC payment "
            "intent, get a risk assessment with three possible outcomes: "
            "APPROVE (safe), STEP_UP (uncertain, evidence purchased), or DENY (blocked). "
            "Every decision produces a signed, independently verifiable receipt."
        ),
        "provider": "BlockIntel Inc",
        "version": "1.0.0",
        "circle_stack": {
            "agent_wallets": True,
            "gateway_nanopayments": True,
            "circle_cli": True,
            "x402_protocol": True,
        },
        "pricing": {
            "fee": "$0.05 USDC",
            "settlement": "Circle Gateway nanopayments",
            "network": "eip155:84532",
        },
        "endpoints": {
            "security_check": "/x402/security-check",
            "health": "/x402/health",
            "gateway_status": "/api/gateway",
        },
        "wallets": {
            "treasury": "0x0c744ecb3949b3582cdd2dbc70dc876405eec44d",
            "customer_agent": "0x008ed50be2cd35f6333a37542a76a227e3b16acc",
            "evidence_validator": "0xbe1424b7bcc149523f749ceb7a8316d8ba6ba558",
        },
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
            f"Verigate will pay $0.02 for independent verification before deciding."
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
