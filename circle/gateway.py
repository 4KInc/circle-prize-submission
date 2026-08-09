"""Circle Gateway nanopayments client.

Integrates with Circle Gateway's facilitator API for gas-free USDC
nanopayments via the x402 protocol. Handles settlement, verification,
and balance queries.

Gateway flow:
1. Buyer signs EIP-3009 offchain authorization (zero gas)
2. Seller calls Gateway facilitator to settle/verify
3. Gateway batches settlements on-chain periodically
4. Both parties get sub-second confirmation

Facilitator API:
  Testnet: https://gateway-api-testnet.circle.com
  Mainnet: https://gateway-api.circle.com
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("circle.gateway")

# Gateway facilitator URLs
GATEWAY_TESTNET = "https://gateway-api-testnet.circle.com"
GATEWAY_MAINNET = "https://gateway-api.circle.com"

GATEWAY_URL = os.environ.get(
    "CIRCLE_GATEWAY_URL",
    GATEWAY_TESTNET,
)


@dataclass
class GatewaySettlement:
    """Result of a Gateway nanopayment settlement."""
    success: bool
    payer: str = ""
    transaction: str = ""
    network: str = ""
    error_reason: str = ""

    @property
    def explorer_url(self) -> str:
        if not self.transaction:
            return ""
        # Gateway returns a UUID, not a tx hash — link to Gateway transfers
        return f"{GATEWAY_URL}/v1/x402/transfers/{self.transaction}"


@dataclass
class GatewayVerification:
    """Result of a Gateway payment verification (read-only)."""
    is_valid: bool
    payer: str = ""
    invalid_reason: str = ""


def _headers() -> dict:
    """Build request headers with optional auth."""
    h = {"Content-Type": "application/json"}
    # Gateway API key (if required for your account)
    api_key = os.environ.get("CIRCLE_GATEWAY_API_KEY")
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def settle_payment(
    payment_payload: dict,
    payment_requirements: dict,
) -> GatewaySettlement:
    """Settle an x402 payment via Circle Gateway.

    Called by the seller to validate the buyer's EIP-3009 authorization
    and trigger settlement through Gateway's batched processing.

    Args:
        payment_payload: The x402 payment payload from the buyer
        payment_requirements: The x402 payment requirements from the seller

    Returns:
        GatewaySettlement with success status and transaction ID
    """
    url = f"{GATEWAY_URL}/v1/x402/settle"
    body = {
        "paymentPayload": payment_payload,
        "paymentRequirements": payment_requirements,
    }

    try:
        resp = httpx.post(url, json=body, headers=_headers(), timeout=30)
        data = resp.json()

        if resp.status_code == 200:
            return GatewaySettlement(
                success=data.get("success", False),
                payer=data.get("payer", ""),
                transaction=data.get("transaction", ""),
                network=data.get("network", ""),
                error_reason=data.get("errorReason", ""),
            )
        else:
            error = data.get("errorReason", data.get("message", str(resp.status_code)))
            logger.warning(f"Gateway settle failed: {error}")
            return GatewaySettlement(success=False, error_reason=error)

    except Exception as e:
        logger.error(f"Gateway settle error: {e}")
        return GatewaySettlement(success=False, error_reason=str(e))


def verify_payment(
    payment_payload: dict,
    payment_requirements: dict,
) -> GatewayVerification:
    """Verify an x402 payment without settling (read-only check).

    Validates signature, amount, and payee. Does NOT check balance or nonce
    (those are verified at settlement time).

    Args:
        payment_payload: The x402 payment payload from the buyer
        payment_requirements: The x402 payment requirements from the seller

    Returns:
        GatewayVerification with validity and payer address
    """
    url = f"{GATEWAY_URL}/v1/x402/verify"
    body = {
        "paymentPayload": payment_payload,
        "paymentRequirements": payment_requirements,
    }

    try:
        resp = httpx.post(url, json=body, headers=_headers(), timeout=15)
        data = resp.json()

        return GatewayVerification(
            is_valid=data.get("isValid", False),
            payer=data.get("payer", ""),
            invalid_reason=data.get("invalidReason", ""),
        )

    except Exception as e:
        logger.error(f"Gateway verify error: {e}")
        return GatewayVerification(is_valid=False, invalid_reason=str(e))


def get_balances(addresses: list[str], network: str = "eip155:84532") -> dict:
    """Get Gateway balances for the given addresses.

    Returns balances across all supported domains.
    """
    url = f"{GATEWAY_URL}/v1/balances"

    # USDC token addresses per network
    usdc_by_network = {
        "eip155:84532": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
        "eip155:8453": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    }
    token = usdc_by_network.get(network, usdc_by_network["eip155:84532"])

    body = {
        "sources": [{"network": network, "address": addr} for addr in addresses],
        "token": token,
    }

    try:
        resp = httpx.post(url, json=body, headers=_headers(), timeout=15)
        return resp.json()
    except Exception as e:
        logger.error(f"Gateway balance check error: {e}")
        return {"error": str(e)}


def get_supported_networks() -> dict:
    """Get x402 supported payment kinds and networks."""
    url = f"{GATEWAY_URL}/v1/x402/supported"

    try:
        resp = httpx.get(url, headers=_headers(), timeout=15)
        return resp.json()
    except Exception as e:
        logger.error(f"Gateway supported check error: {e}")
        return {"error": str(e)}


def get_transfer(transfer_id: str) -> dict:
    """Get details of a specific x402 transfer."""
    url = f"{GATEWAY_URL}/v1/x402/transfers/{transfer_id}"

    try:
        resp = httpx.get(url, headers=_headers(), timeout=15)
        return resp.json()
    except Exception as e:
        logger.error(f"Gateway transfer lookup error: {e}")
        return {"error": str(e)}


def search_transfers(
    seller: str | None = None,
    buyer: str | None = None,
    network: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search x402 transfers with filters."""
    url = f"{GATEWAY_URL}/v1/x402/transfers"
    params: dict[str, Any] = {"pageSize": limit}
    if seller:
        params["to"] = seller
    if buyer:
        params["from"] = buyer
    if network:
        params["network"] = network

    try:
        resp = httpx.get(url, params=params, headers=_headers(), timeout=15)
        data = resp.json()
        return data.get("transfers", [])
    except Exception as e:
        logger.error(f"Gateway transfer search error: {e}")
        return []


def build_payment_requirements(
    seller_address: str,
    amount_usdc: str,
    network: str = "eip155:84532",
    asset: str | None = None,
) -> dict:
    """Build x402 v2 payment requirements for Gateway nanopayments.

    This uses the GatewayWalletBatched scheme for Circle Gateway
    nanopayment settlement (vs the standard 'exact' scheme).
    """
    import time

    # USDC contract addresses
    usdc_by_network = {
        "eip155:84532": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",  # Base Sepolia
        "eip155:8453": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",   # Base mainnet
    }

    if asset is None:
        asset = usdc_by_network.get(network, usdc_by_network["eip155:84532"])

    # Convert dollar amount to USDC micro-units (6 decimals)
    amount_micro = str(int(float(amount_usdc) * 1_000_000))

    return {
        "scheme": "exact",
        "network": network,
        "asset": asset,
        "payTo": seller_address,
        "amount": amount_micro,
        "maxTimeoutSeconds": int(time.time()) + 300,
        "extra": {
            "name": "USD Coin",
            "version": "2",
        },
    }
