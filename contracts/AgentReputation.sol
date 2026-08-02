// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.20;

/**
 * @title AgentReputation — ERC-8004 compatible agent reputation registry
 * @notice Stores on-chain reputation events for AI agents.
 *         When Verigate's Forensic Recorder documents an incident,
 *         it publishes a signed event to this contract. Other operators
 *         can query an agent's on-chain track record before transacting.
 *
 *         This is a minimal implementation matching the ERC-8004 data model.
 *         Events are stored as indexed logs for efficient querying.
 */
contract AgentReputation {
    struct ReputationEntry {
        address reporter;
        string agentId;
        string eventType;
        string severity;
        string metadata;
        uint256 timestamp;
    }

    // All reputation entries
    ReputationEntry[] public entries;

    // Agent ID => entry indices
    mapping(bytes32 => uint256[]) private _agentEntries;

    // Events (indexed for Basescan visibility)
    event ReputationRecorded(
        address indexed reporter,
        string indexed agentIdHash,
        string agentId,
        string eventType,
        string severity,
        string metadata,
        uint256 timestamp
    );

    /**
     * @notice Record a reputation event for an agent.
     * @param agentId The agent identifier
     * @param eventType Event type (e.g., "ISOLATION", "POLICY_VIOLATION")
     * @param severity Severity level ("LOW", "MEDIUM", "HIGH", "CRITICAL")
     * @param metadata JSON-encoded forensic metadata (record_id, receipt_hash, etc.)
     */
    function recordEvent(
        string calldata agentId,
        string calldata eventType,
        string calldata severity,
        string calldata metadata
    ) external {
        uint256 idx = entries.length;
        entries.push(ReputationEntry({
            reporter: msg.sender,
            agentId: agentId,
            eventType: eventType,
            severity: severity,
            metadata: metadata,
            timestamp: block.timestamp
        }));

        bytes32 agentHash = keccak256(bytes(agentId));
        _agentEntries[agentHash].push(idx);

        emit ReputationRecorded(
            msg.sender,
            agentId,
            agentId,
            eventType,
            severity,
            metadata,
            block.timestamp
        );
    }

    /**
     * @notice Get the number of entries for an agent.
     */
    function getAgentEntryCount(string calldata agentId) external view returns (uint256) {
        return _agentEntries[keccak256(bytes(agentId))].length;
    }

    /**
     * @notice Get total number of reputation entries.
     */
    function totalEntries() external view returns (uint256) {
        return entries.length;
    }
}
