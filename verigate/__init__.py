"""Verigate SDK — cryptographic proof for AI agent payments.

Usage:
    from verigate import Gate, screen

    # Quick screening
    result = screen({"from": "my-agent", "to": "vendor", "amount": 500, "currency": "USDC"})

    # Full gate
    gate = Gate("circle://agent-wallet")
    receipt = gate.authorize(intent)
    gate.verify()
"""

from verigate.gate import Gate, Intent, VerifyResult

import os as _os
import json as _json


def screen(payment: dict, *, base_url: str | None = None) -> dict:
    """Screen a payment intent before executing.

    Args:
        payment: dict with keys like from, to, amount, currency, purpose, service, reason.
        base_url: Verigate API URL (default: VERIGATE_URL env or https://verigate.cloud).

    Returns:
        dict with verdict, risk_score, receipt_hash, fee, reasoning.
    """
    url = base_url or _os.environ.get("VERIGATE_URL", "https://verigate.cloud")

    # Normalize keys: support both "to"/"from" and "payee"/"source" styles
    payee = payment.get("to") or payment.get("payee", "")
    amount = payment.get("amount", "0")
    service = payment.get("service") or payment.get("purpose", "")
    reason = payment.get("reason", "")

    # Try remote API first
    try:
        import httpx

        resp = httpx.post(
            f"{url}/api/check",
            json={"payee": payee, "amount": str(amount), "service": service, "reason": reason},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "verdict": data.get("decision", "DENY"),
                "risk_score": data.get("score", 100),
                "receipt_hash": data.get("receipt_hash", ""),
                "fee": "$0.05",
                "reasoning": data.get("rationale", ""),
                "signals": data.get("signals", []),
                "band": data.get("band", ""),
                "raw": data,
            }
    except Exception:
        pass

    # Offline fallback: use local scorer
    try:
        from circle.risk_scorer import evaluate_risk

        risk = evaluate_risk(
            payee=payee,
            amount=str(amount),
            service=service,
            reason=reason,
            source_wallet="0x0000000000000000000000000000000000000000",
            chain="BASE",
        )
        return {
            "verdict": risk.decision,
            "risk_score": risk.score,
            "receipt_hash": "",
            "fee": "$0.05",
            "reasoning": risk.rationale,
            "signals": risk.signals,
            "band": risk.band,
            "raw": {"decision": risk.decision, "score": risk.score, "band": risk.band},
        }
    except Exception as e:
        return {
            "verdict": "DENY",
            "risk_score": 100,
            "receipt_hash": "",
            "fee": "$0.05",
            "reasoning": f"Screening unavailable: {e}",
            "signals": ["offline"],
            "band": "CRITICAL",
            "raw": {},
        }


__all__ = ["Gate", "Intent", "VerifyResult", "screen"]
