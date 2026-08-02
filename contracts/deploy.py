#!/usr/bin/env python3
"""Deploy AgentReputation contract to Base Sepolia.

Uses py-solc-x for compilation and web3.py for deployment.
The deployer is a local wallet imported via Circle CLI.
"""

import json
import os
import sys
from pathlib import Path

def compile_contract():
    """Compile the Solidity contract."""
    from solcx import compile_standard, install_solc

    print("Installing solc 0.8.20...")
    install_solc("0.8.20")

    contract_path = Path(__file__).parent / "AgentReputation.sol"
    source = contract_path.read_text()

    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {"AgentReputation.sol": {"content": source}},
            "settings": {
                "outputSelection": {
                    "*": {"*": ["abi", "evm.bytecode.object"]}
                },
                "optimizer": {"enabled": True, "runs": 200},
            },
        },
        solc_version="0.8.20",
    )

    contract_data = compiled["contracts"]["AgentReputation.sol"]["AgentReputation"]
    abi = contract_data["abi"]
    bytecode = contract_data["evm"]["bytecode"]["object"]

    # Save ABI for later use
    abi_path = Path(__file__).parent / "AgentReputation.abi.json"
    abi_path.write_text(json.dumps(abi, indent=2))
    print(f"ABI saved to {abi_path}")

    return abi, bytecode


def deploy(abi, bytecode):
    """Deploy to Base Sepolia using web3.py + a local private key."""
    from web3 import Web3

    rpc_url = os.environ.get("BASE_SEPOLIA_RPC", "https://sepolia.base.org")
    private_key = os.environ.get("DEPLOYER_PRIVATE_KEY")

    if not private_key:
        print("\nERROR: Set DEPLOYER_PRIVATE_KEY env var to deploy.")
        print("You can import a local wallet via: circle wallet import")
        print("Or use any funded Base Sepolia EOA private key.")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"ERROR: Cannot connect to {rpc_url}")
        sys.exit(1)

    account = w3.eth.account.from_key(private_key)
    print(f"Deployer: {account.address}")
    print(f"Balance: {w3.eth.get_balance(account.address) / 1e18:.6f} ETH")

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = contract.constructor().build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.eth.gas_price,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Deploy tx: {tx_hash.hex()}")
    print("Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    contract_address = receipt["contractAddress"]

    print(f"\n{'=' * 60}")
    print(f"AgentReputation deployed!")
    print(f"  Address:  {contract_address}")
    print(f"  Tx:       https://sepolia.basescan.org/tx/{tx_hash.hex()}")
    print(f"  Contract: https://sepolia.basescan.org/address/{contract_address}")
    print(f"{'=' * 60}")

    # Save deployment info
    deploy_info = {
        "address": contract_address,
        "chain": "BASE-SEPOLIA",
        "tx_hash": tx_hash.hex(),
        "deployer": account.address,
        "explorer": f"https://sepolia.basescan.org/address/{contract_address}",
    }
    info_path = Path(__file__).parent / "deployment.json"
    info_path.write_text(json.dumps(deploy_info, indent=2))
    print(f"\nDeployment info saved to {info_path}")

    return contract_address


if __name__ == "__main__":
    abi, bytecode = compile_contract()
    deploy(abi, bytecode)
