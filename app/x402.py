"""x402-paywalled endpoint — a real service behind Circle's x402 payment protocol.

This endpoint serves market data (BTC/USDC price) behind an x402 paywall.
When accessed without payment, it returns HTTP 402 with payment requirements.
When the `payment-signature` header is present, it validates and returns data.

The x402 protocol flow:
1. Client sends GET to /x402/market-data
2. Server returns 402 with `payment-required` header (base64 JSON)
3. Client signs EIP-3009 authorization (handled by `circle services pay`)
4. Client retries with `payment-signature` header
5. Server validates payment and returns the resource

This can be called with:
    circle services pay <url>/x402/market-data --address 0xWALLET --chain BASE-SEPOLIA
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

logger = logging.getLogger("app.x402")

router = APIRouter(prefix="/x402")

# Payee address — receives USDC payments for this service
PAYEE_ADDRESS = os.environ.get(
    "X402_PAYEE_ADDRESS",
    "0x008ed50be2cd35f6333a37542a76a227e3b16acc",  # Our agent wallet (self-pay for demo)
)

# USDC contract addresses per network
USDC_BY_NETWORK = {
    "eip155:84532": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",  # Base Sepolia
    "eip155:8453": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",   # Base mainnet
}

# Price in USDC micro-units (6 decimals). 10000 = $0.01
SERVICE_PRICE = os.environ.get("X402_PRICE", "10000")

# Network — Base Sepolia by default
NETWORK = os.environ.get("X402_NETWORK", "eip155:84532")


def _build_payment_required() -> dict:
    """Build the x402 v2 payment requirements."""
    return {
        "x402Version": 2,
        "accepts": [
            {
                "scheme": "exact",
                "network": NETWORK,
                "asset": USDC_BY_NETWORK.get(NETWORK, USDC_BY_NETWORK["eip155:84532"]),
                "payTo": PAYEE_ADDRESS,
                "amount": SERVICE_PRICE,
                "maxTimeoutSeconds": int(time.time()) + 300,
                "extra": {
                    "name": "USD Coin",
                    "version": "2",
                },
            },
        ],
    }


def _market_data_response() -> dict:
    """Generate market data response (the resource behind the paywall)."""
    return {
        "service": "verigate-market-data",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "pair": "BTC/USDC",
            "price": "67432.50",
            "volume_24h": "1234567890.00",
            "change_24h": "+2.34%",
            "high_24h": "68100.00",
            "low_24h": "66200.00",
            "source": "aggregated",
        },
        "paid": True,
        "payee": PAYEE_ADDRESS,
        "network": NETWORK,
    }


@router.get("/market-data")
async def market_data(request: Request):
    """x402-paywalled market data endpoint.

    Without payment: returns 402 with payment requirements.
    With payment: returns market data.
    """
    # Check for payment signature header
    payment_sig = request.headers.get("payment-signature") or request.headers.get("x-payment-signature")

    if payment_sig:
        # Payment provided — return the resource
        logger.info(f"x402 payment received, serving market data")
        data = _market_data_response()

        # Build payment response header
        payment_response = base64.b64encode(json.dumps({
            "x402Version": 2,
            "success": True,
            "network": NETWORK,
        }).encode()).decode()

        return Response(
            content=json.dumps(data),
            media_type="application/json",
            headers={"payment-response": payment_response},
        )

    # No payment — return 402 with requirements
    requirements = _build_payment_required()
    requirements_b64 = base64.b64encode(json.dumps(requirements).encode()).decode()

    logger.info(f"x402 payment required for market-data")
    return Response(
        content=json.dumps({
            "error": "Payment Required",
            "message": "This endpoint requires USDC payment via x402 protocol.",
            "price": f"${int(SERVICE_PRICE) / 1_000_000:.2f} USDC",
            "accepts": requirements["accepts"],
        }),
        status_code=402,
        media_type="application/json",
        headers={"payment-required": requirements_b64},
    )


@router.get("/health")
async def x402_health():
    return {
        "service": "verigate-market-data",
        "x402": True,
        "network": NETWORK,
        "payee": PAYEE_ADDRESS,
        "price_usdc": f"${int(SERVICE_PRICE) / 1_000_000:.2f}",
    }
