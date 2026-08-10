"""ERC-8004 reputation writer — REAL ON-CHAIN IMPLEMENTATION.

Publishes forensic events to a deployed AgentReputation smart contract
on Base Sepolia. Every reputation event is a real on-chain transaction
viewable on Basescan.

Contract: 0xf5FE7BF0163328BA0011Fa49Caf3707434E145AA
Explorer: https://sepolia.basescan.org/address/0xf5FE7BF0163328BA0011Fa49Caf3707434E145AA
Source:   contracts/AgentReputation.sol

When Verigate's Forensic Recorder documents an incident, it publishes
a signed reputation event to this contract. Other operators can query
the contract to check an agent's on-chain track record.

The contract implements the ERC-8004 data model:
- recordEvent(agentId, eventType, severity, metadata)
- Emits ReputationRecorded event (indexed by reporter and agentId)
- getAgentEntryCount(agentId) for querying history
- totalEntries() for registry size
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("circle.reputation")


@dataclass
class ReputationEvent:
    """An ERC-8004 reputation event for an agent."""
    event_id: str
    agent_id: str
    event_type: str              # "ISOLATION" | "POLICY_VIOLATION" | "GOOD_STANDING"
    severity: str                # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    source: str                  # "verigate" — the system that produced this event
    isolation_id: str | None     # Link to the IsolationRecord
    receipt_hash: str            # Cryptographic proof reference
    reason: str
    timestamp: str
    tx_hash: str | None = None   # On-chain tx if published
    published: bool = False

    def to_erc8004_payload(self) -> dict:
        """Format as an ERC-8004 registry submission."""
        return {
            "agentId": self.agent_id,
            "eventType": self.event_type,
            "severity": self.severity,
            "source": self.source,
            "metadata": json.dumps({
                "event_id": self.event_id,
                "isolation_id": self.isolation_id,
                "receipt_hash": self.receipt_hash,
                "reason": self.reason,
                "timestamp": self.timestamp,
                "schema": "verigate-reputation-v0.1",
            }, sort_keys=True, separators=(",", ":")),
        }

    def event_hash(self) -> str:
        payload_bytes = json.dumps(
            self.to_erc8004_payload(), sort_keys=True, separators=(",", ":"),
        ).encode()
        return "sha256:" + hashlib.sha256(payload_bytes).hexdigest()


class ReputationWriter:
    """Publishes agent reputation events to ERC-8004 registries.

    On testnet: stores events locally and logs the contract call
    that would be made.
    On mainnet: submits the event to the ERC-8004 contract via
    Circle CLI or direct contract interaction.
    """

    def __init__(
        self,
        chain: str = "BASE-SEPOLIA",
        registry_address: str | None = None,
        wallet_address: str | None = None,
    ):
        self.chain = chain
        self.registry_address = registry_address
        self.wallet_address = wallet_address
        self.events: list[ReputationEvent] = []

    def publish_isolation(
        self,
        agent_id: str,
        severity: str,
        isolation_id: str,
        receipt_hash: str,
        reason: str,
    ) -> ReputationEvent:
        """Publish an isolation event to the ERC-8004 registry."""
        event = ReputationEvent(
            event_id=f"rep-{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            event_type="ISOLATION",
            severity=severity,
            source="verigate",
            isolation_id=isolation_id,
            receipt_hash=receipt_hash,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Attempt on-chain publication
        tx_hash = self._submit_to_registry(event)
        if tx_hash:
            event.tx_hash = tx_hash
            event.published = True

        self.events.append(event)
        logger.info(
            f"Reputation event {event.event_id}: agent={agent_id} "
            f"severity={severity} published={event.published}"
        )
        return event

    # Deployed AgentReputation contract on Base Sepolia
    REGISTRY_BASE_SEPOLIA = "0xf5FE7BF0163328BA0011Fa49Caf3707434E145AA"

    def _submit_to_registry(self, event: ReputationEvent) -> str | None:
        """Submit event to the AgentReputation contract on Base Sepolia.

        Requires ERC8004_DEPLOYER_KEY env var. Returns None if not set
        or if submission fails. No fabricated hashes — either real tx or None.
        Contract: https://sepolia.basescan.org/address/0xf5FE7BF0163328BA0011Fa49Caf3707434E145AA
        """
        payload = event.to_erc8004_payload()

        # Use the deployed contract on Base Sepolia
        registry = self.registry_address or self.REGISTRY_BASE_SEPOLIA

        import os
        deployer_key = os.environ.get("ERC8004_DEPLOYER_KEY")
        if not deployer_key:
            logger.info("ERC8004_DEPLOYER_KEY not set — skipping on-chain submission")
            return None

        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider("https://base-sepolia-rpc.publicnode.com"))
            if not w3.is_connected():
                logger.warning("Cannot connect to Base Sepolia RPC")
                return None

            account = w3.eth.account.from_key(deployer_key)

            # Encode the function call
            from eth_abi import encode
            func_sig = w3.keccak(text="recordEvent(string,string,string,string)")[:4]
            encoded_args = encode(
                ["string", "string", "string", "string"],
                [payload["agentId"], payload["eventType"], payload["severity"], payload["metadata"]],
            )

            tx = {
                "to": Web3.to_checksum_address(registry),
                "from": account.address,
                "data": func_sig + encoded_args,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 500_000,
                "maxFeePerGas": w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": 1_000_000,
                "chainId": 84532,
            }

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hex = tx_hash.hex()

            logger.info(
                f"ERC-8004 on-chain tx: https://sepolia.basescan.org/tx/{tx_hex}"
            )
            return tx_hex

        except Exception as e:
            logger.warning(f"ERC-8004 on-chain submission failed: {e}")
            return None

    def get_agent_history(self, agent_id: str) -> list[ReputationEvent]:
        """Get all reputation events for a specific agent."""
        return [e for e in self.events if e.agent_id == agent_id]
