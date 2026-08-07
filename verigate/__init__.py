"""Verigate SDK — cryptographic proof for AI agent payments.

Usage:
    from verigate import Gate

    gate = Gate("circle://agent-wallet")
    receipt = gate.authorize(intent)
    gate.verify()
"""

from verigate.gate import Gate, Intent, VerifyResult

__all__ = ["Gate", "Intent", "VerifyResult"]
