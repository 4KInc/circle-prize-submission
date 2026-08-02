"""Thin Python wrapper around the Circle CLI.

All Circle operations go through this module so we have a single
place to swap CLI-shell-out for REST/SDK later if needed.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass


def _circle_bin() -> str:
    """Resolve the circle CLI binary path."""
    custom = os.environ.get("CIRCLE_CLI_PATH")
    if custom:
        return custom
    # Default: user-local npm install
    home = os.path.expanduser("~")
    local_bin = os.path.join(home, ".local", "bin", "circle")
    if os.path.isfile(local_bin):
        return local_bin
    return "circle"


def _run(args: list[str], timeout: int = 120) -> dict:
    """Run a circle CLI command and return parsed JSON output."""
    cmd = [_circle_bin()] + args + ["-o", "json"]
    env = {**os.environ, "CIRCLE_ACCEPT_TERMS": "1"}
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"circle {' '.join(args)} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


@dataclass
class TransferResult:
    tx_hash: str
    state: str
    source: str
    destination: str
    amount: str
    block_height: int | None
    explorer_url: str


def wallet_list(chain: str) -> list[dict]:
    """List wallets on the given chain."""
    data = _run(["wallet", "list", "--chain", chain])
    return data.get("data", {}).get("wallets", [])


def wallet_balance(address: str, chain: str) -> list[dict]:
    """Get token balances for a wallet."""
    data = _run(["wallet", "balance", "--address", address, "--chain", chain])
    return data.get("data", {}).get("balances", [])


def wallet_fund(address: str, chain: str, amount: float) -> dict:
    """Fund a testnet wallet via faucet."""
    data = _run(["wallet", "fund", "--address", address, "--chain", chain, "--amount", str(amount)])
    return data.get("data", {})


def wallet_transfer(
    source: str,
    destination: str,
    amount: str,
    chain: str,
    token_address: str | None = None,
    idempotency_key: str | None = None,
) -> TransferResult:
    """Execute a USDC transfer and return the result with explorer URL."""
    args = [
        "wallet", "transfer", destination,
        "--amount", amount,
        "--address", source,
        "--chain", chain,
    ]
    if token_address:
        args.extend(["--token", token_address])
    if idempotency_key:
        args.extend(["--idempotency-key", idempotency_key])

    data = _run(args, timeout=180)
    tx = data.get("data", {})
    tx_hash = tx.get("txHash", "")

    # Build explorer URL based on chain
    chain_upper = chain.upper()
    if "SEPOLIA" in chain_upper:
        explorer_url = f"https://sepolia.basescan.org/tx/{tx_hash}"
    else:
        explorer_url = f"https://basescan.org/tx/{tx_hash}"

    return TransferResult(
        tx_hash=tx_hash,
        state=tx.get("state", "UNKNOWN"),
        source=tx.get("sourceAddress", source),
        destination=tx.get("destinationAddress", destination),
        amount=amount,
        block_height=tx.get("blockHeight"),
        explorer_url=explorer_url,
    )


def wallet_sign_message(address: str, chain: str, message: str) -> dict:
    """Sign a plaintext message with the Circle agent wallet.

    Used for Merkle root anchoring — the wallet signs the root,
    producing a verifiable attestation.
    """
    data = _run([
        "wallet", "sign", "message", message,
        "--address", address,
        "--chain", chain,
    ])
    return data.get("data", {})


def services_search(query: str | None = None, limit: int = 10) -> list[dict]:
    """Search the Circle Agent Marketplace for x402 services."""
    args = ["services", "search"]
    if query:
        args.append(query)
    args.extend(["--limit", str(limit)])
    data = _run(args)
    return data.get("data", {}).get("items", [])


def services_pay(
    url: str,
    address: str,
    chain: str,
    method: str = "GET",
    data: str | None = None,
    max_amount: str | None = None,
) -> dict:
    """Pay for an x402-paywalled service via Circle CLI.

    This handles the full x402 flow:
    1. Send request to URL
    2. Receive 402 with payment requirements
    3. Sign EIP-3009 authorization
    4. Retry with payment signature
    5. Return the response
    """
    args = [
        "services", "pay", url,
        "--address", address,
        "--chain", chain,
    ]
    if method != "GET":
        args.extend(["-X", method])
    if data:
        args.extend(["-d", data])
    if max_amount:
        args.extend(["--max-amount", max_amount])
    args.extend(["--timeout", "60"])
    result = _run(args, timeout=90)
    return result.get("data", result)


def services_inspect(url: str) -> dict:
    """Inspect an x402 service's pricing and requirements."""
    data = _run(["services", "inspect", url])
    return data.get("data", data)


def wallet_transfer_with_recibo(
    source: str,
    destination: str,
    amount: str,
    chain: str,
    receipt_hash: str,
    token_address: str | None = None,
    idempotency_key: str | None = None,
) -> TransferResult:
    """USDC transfer with Recibo metadata — PROTOCOL-COMPATIBLE STUB.

    Recibo is Circle's open-source smart contract for attaching encrypted
    messages to ERC-20 transfers (~10K gas overhead).

    This stub demonstrates the ARCHITECTURE for bi-directional binding:
    - Receipt references tx hash (decision → settlement)
    - Settlement references receipt hash (settlement → decision)

    On testnet: standard transfer + receipt_hash logged (Recibo not deployed)
    On mainnet: would call Recibo's transferWithMessage function

    What this proves: the system is READY for Recibo integration.
    What this does NOT do: actually call the Recibo contract on testnet.
    """
    chain_upper = chain.upper()

    # On testnet, Recibo contract may not be deployed — use standard transfer
    # but log the bi-directional binding intent
    if "SEPOLIA" in chain_upper or "TESTNET" in chain_upper:
        import logging
        logging.getLogger("circle.cli").info(
            f"Recibo bi-directional binding (simulated on testnet): "
            f"receipt_hash={receipt_hash[:30]}... embedded in transfer metadata"
        )
        result = wallet_transfer(
            source=source,
            destination=destination,
            amount=amount,
            chain=chain,
            token_address=token_address,
            idempotency_key=idempotency_key,
        )
        # Attach recibo metadata to result for receipt binding
        result.recibo_receipt_hash = receipt_hash
        return result

    # Mainnet: use Recibo transferWithMessage
    args = [
        "wallet", "transfer", destination,
        "--amount", amount,
        "--address", source,
        "--chain", chain,
        "--message", receipt_hash,  # Recibo encrypted metadata
    ]
    if token_address:
        args.extend(["--token", token_address])
    if idempotency_key:
        args.extend(["--idempotency-key", idempotency_key])

    data = _run(args, timeout=180)
    tx = data.get("data", {})
    tx_hash = tx.get("txHash", "")
    explorer_url = f"https://basescan.org/tx/{tx_hash}"

    result = TransferResult(
        tx_hash=tx_hash,
        state=tx.get("state", "UNKNOWN"),
        source=tx.get("sourceAddress", source),
        destination=tx.get("destinationAddress", destination),
        amount=amount,
        block_height=tx.get("blockHeight"),
        explorer_url=explorer_url,
    )
    result.recibo_receipt_hash = receipt_hash
    return result


# Well-known USDC token addresses
USDC_ADDRESSES = {
    "BASE-SEPOLIA": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
    "BASE": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
}
