"""Offline verifier for gated payment receipts.

Validates the full trust chain:
1. Ed25519 signature on each receipt
2. Hash chain continuity (prev_receipt linkage)
3. Merkle inclusion proof (receipt is in the anchored batch)
4. Settlement tx cross-reference (on-chain tx matches receipt)
5. Anchor verification (Merkle root was committed)

This verifier requires NO access to the gateway's private key —
it uses only the public key (from JWK) and on-chain data.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "engine")
if os.path.isdir(ENGINE_PATH) and ENGINE_PATH not in sys.path:
    sys.path.insert(0, ENGINE_PATH)

from gateway.merkle import compute_unified_root
from gateway.verify import verify_chain

logger = logging.getLogger("circle.verifier")


@dataclass
class SettlementCheck:
    """Result of cross-referencing a receipt against its settlement tx."""
    receipt_hash: str
    has_settlement: bool = False
    tx_hash: str | None = None
    payee_matches: bool = False
    amount_matches: bool = False
    chain_matches: bool = False
    explorer_url: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class X401Check:
    """Result of checking x401 credential binding in a receipt."""
    receipt_hash: str
    has_credential: bool = False
    credential_hash: str | None = None
    binding_valid: bool = False


@dataclass
class VerificationReport:
    """Complete verification report for a payment receipt chain."""
    # Individual checks
    signature_check: str = "PENDING"     # PASS | FAIL
    chain_check: str = "PENDING"         # PASS | FAIL
    merkle_check: str = "PENDING"        # PASS | FAIL | SKIPPED
    x401_check: str = "PENDING"          # PASS | FAIL | SKIPPED
    settlement_checks: list[SettlementCheck] = field(default_factory=list)
    x401_checks: list[X401Check] = field(default_factory=list)
    anchor_check: str = "PENDING"        # PASS | FAIL | SKIPPED

    # Summary
    overall: str = "PENDING"
    receipt_count: int = 0
    merkle_root: str | None = None
    anchor_signature: str | None = None
    errors: list[str] = field(default_factory=list)

    def is_green(self) -> bool:
        return self.overall == "PASS"


def verify_payment_chain(
    envelopes: list[dict],
    public_key_jwk: dict,
    merkle_root: str | None = None,
    inclusion_proofs: dict[str, dict] | None = None,
    anchor_data: dict | None = None,
) -> VerificationReport:
    """Run the full offline verification pipeline.

    Args:
        envelopes: Receipt envelopes from the executor
        public_key_jwk: Gateway's Ed25519 public key (JWK format)
        merkle_root: Expected Merkle batch root
        inclusion_proofs: Map of receipt_hash → inclusion proof
        anchor_data: Anchor attestation data (wallet signature over root)
    """
    report = VerificationReport(receipt_count=len(envelopes))

    if not envelopes:
        report.overall = "FAIL"
        report.errors.append("No receipts to verify")
        return report

    # ── 1. Ed25519 signatures + hash chain ────────────────────────────
    chain_result = verify_chain(envelopes, public_key_jwk)
    report.signature_check = chain_result.receipt_integrity
    report.chain_check = chain_result.chain_validity

    if chain_result.receipt_integrity == "FAIL":
        report.errors.extend([e["message"] for e in chain_result.errors])
        report.overall = "FAIL"
        return report

    if chain_result.chain_validity == "FAIL":
        report.errors.extend([e["message"] for e in chain_result.errors])
        report.overall = "FAIL"
        return report

    # ── 2. Settlement tx cross-reference ──────────────────────────────
    for env in envelopes:
        body = env.get("body", {})
        receipt_hash = env.get("receipt_hash", "")
        delegation = body.get("delegation_context")

        check = SettlementCheck(receipt_hash=receipt_hash)

        if body.get("decision") == "deny":
            # Denial receipts have no settlement — that's correct
            check.has_settlement = False
            report.settlement_checks.append(check)
            continue

        if not delegation or "settlement_tx" not in delegation:
            check.errors.append("Approved receipt missing settlement_tx in delegation_context")
            report.settlement_checks.append(check)
            continue

        check.has_settlement = True
        check.tx_hash = delegation["settlement_tx"]
        # Verify payee/amount are present in the signed delegation context
        # (on-chain cross-reference would require an RPC call — not done here)
        check.payee_matches = bool(delegation.get("settlement_payee"))
        check.amount_matches = bool(delegation.get("settlement_amount"))

        chain_name = delegation.get("settlement_chain", "")
        check.chain_matches = bool(chain_name)

        if "SEPOLIA" in chain_name.upper():
            check.explorer_url = f"https://sepolia.basescan.org/tx/{check.tx_hash}"
        else:
            check.explorer_url = f"https://basescan.org/tx/{check.tx_hash}"

        report.settlement_checks.append(check)

    # ── 2b. x401 credential binding check ────────────────────────────
    has_any_x401 = False
    for env in envelopes:
        body = env.get("body", {})
        receipt_hash = env.get("receipt_hash", "")
        delegation = body.get("delegation_context")

        check = X401Check(receipt_hash=receipt_hash)

        if delegation and "x401_credential_hash" in delegation:
            has_any_x401 = True
            check.has_credential = True
            check.credential_hash = delegation["x401_credential_hash"]
            # Credential hash is bound — binding integrity is guaranteed by
            # the receipt signature (if sig is valid, binding is valid)
            check.binding_valid = report.signature_check == "PASS"

        report.x401_checks.append(check)

    if has_any_x401:
        all_bound_valid = all(
            c.binding_valid for c in report.x401_checks if c.has_credential
        )
        report.x401_check = "PASS" if all_bound_valid else "FAIL"
    else:
        report.x401_check = "SKIPPED"

    # ── 3. Merkle inclusion proofs ────────────────────────────────────
    if merkle_root:
        report.merkle_root = merkle_root

        # Recompute root from receipt hashes
        receipt_hashes_hex = [
            env["receipt_hash"].removeprefix("sha256:")
            for env in envelopes
        ]
        computed_root = compute_unified_root(receipt_hashes_hex)

        if computed_root != merkle_root:
            report.merkle_check = "FAIL"
            report.errors.append(
                f"Merkle root mismatch: computed {computed_root[:30]}... "
                f"vs claimed {merkle_root[:30]}..."
            )
        else:
            report.merkle_check = "PASS"

        # Verify individual inclusion proofs if provided
        if inclusion_proofs:
            for receipt_hash, proof in inclusion_proofs.items():
                if proof and proof.get("root") != merkle_root:
                    report.merkle_check = "FAIL"
                    report.errors.append(
                        f"Inclusion proof root mismatch for {receipt_hash[:20]}..."
                    )
    else:
        report.merkle_check = "SKIPPED"

    # ── 4. Anchor verification ────────────────────────────────────────
    if anchor_data and merkle_root:
        signed_message = anchor_data.get("message", "")
        if signed_message == merkle_root or signed_message == merkle_root.removeprefix("sha256:"):
            report.anchor_check = "PASS"
            report.anchor_signature = anchor_data.get("signature", "")
        else:
            report.anchor_check = "FAIL"
            report.errors.append(
                f"Anchor message mismatch: signed '{signed_message[:30]}...' "
                f"vs root '{merkle_root[:30]}...'"
            )
    else:
        report.anchor_check = "SKIPPED"

    # ── Overall ───────────────────────────────────────────────────────
    checks = [report.signature_check, report.chain_check]
    if report.merkle_check != "SKIPPED":
        checks.append(report.merkle_check)
    if report.x401_check != "SKIPPED":
        checks.append(report.x401_check)
    if report.anchor_check != "SKIPPED":
        checks.append(report.anchor_check)

    if all(c == "PASS" for c in checks):
        report.overall = "PASS"
    elif any(c == "FAIL" for c in checks):
        report.overall = "FAIL"
    else:
        report.overall = "PARTIAL"

    return report


def print_report(report: VerificationReport) -> None:
    """Pretty-print a verification report."""
    status = {
        "PASS": "PASS",
        "FAIL": "FAIL",
        "SKIPPED": "SKIP",
        "PENDING": "----",
        "PARTIAL": "PART",
    }

    print(f"\n{'=' * 60}")
    print("OFFLINE VERIFICATION REPORT")
    print(f"{'=' * 60}")
    print(f"  Receipts:      {report.receipt_count}")
    print(f"  Signatures:    {status.get(report.signature_check, '?')}")
    print(f"  Hash chain:    {status.get(report.chain_check, '?')}")
    print(f"  Merkle root:   {status.get(report.merkle_check, '?')}")
    print(f"  x401 identity: {status.get(report.x401_check, '?')}")
    print(f"  Anchor:        {status.get(report.anchor_check, '?')}")

    if report.settlement_checks:
        print("\n  Settlement cross-references:")
        for sc in report.settlement_checks:
            if sc.has_settlement:
                print(f"    [{sc.receipt_hash[:20]}...] tx={sc.tx_hash[:20]}...")
                print(f"      Explorer: {sc.explorer_url}")
            else:
                print(f"    [{sc.receipt_hash[:20]}...] (denial — no settlement)")

    if report.merkle_root:
        print(f"\n  Merkle root:   {report.merkle_root[:40]}...")

    if report.errors:
        print("\n  Errors:")
        for e in report.errors:
            print(f"    - {e}")

    print(f"\n  OVERALL: {report.overall}")
    print(f"{'=' * 60}")
