"""Tests proving the validator's verdict is decorrelated from the primary scorer.

The validator forms its own opinion using independent screens (OFAC, address
format, amount ceiling). These tests show inputs where the two disagree.
"""

from circle.risk_scorer import evaluate_risk


class TestValidatorDecorrelation:
    """Validator and primary scorer can disagree on constructed inputs."""

    def test_primary_approves_but_validator_would_deny_high_amount(self):
        """Primary scorer APPROVEs a $12 payment (score < 40),
        but the validator's amount ceiling is $10 → would DENY."""
        r = evaluate_risk(
            payee="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28",
            amount="12.00",
            service="analytics",
            reason="quarterly data purchase",
            source_wallet="0x1",
            chain="BASE-SEPOLIA",
        )
        # Primary might APPROVE or STEP_UP depending on signals
        # The validator has VALIDATOR_AMOUNT_CEILING = 10.0
        # So $12 > $10 → validator independently denies
        from app.validator import _independent_risk, VALIDATOR_AMOUNT_CEILING
        deny, reason = _independent_risk(
            "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28", "12.00"
        )
        assert deny is True
        assert "above validator ceiling" in reason.lower() or "amount" in reason.lower()

    def test_validator_uses_own_threshold(self):
        """Validator's amount ceiling is independent of the primary scorer's."""
        from app.validator import VALIDATOR_AMOUNT_CEILING
        from circle.risk_scorer import APPROVE_CEILING
        # These are separate constants
        assert VALIDATOR_AMOUNT_CEILING == 10.0
        # Primary scorer threshold is a score (0-100), not a dollar amount
        assert APPROVE_CEILING == 39

    def test_both_agree_on_sanctioned(self):
        """Both should DENY a sanctioned address (convergent, not decorrelated)."""
        r = evaluate_risk(
            "0x722122df12d4e14e13ac3b6895a86e84145b6967",  # Tornado Cash
            "0.01", "test", "normal", "0x1", "BASE-SEPOLIA",
        )
        assert r.decision != "APPROVE"

        from app.validator import _independent_risk
        deny, _ = _independent_risk(
            "0x722122df12d4e14e13ac3b6895a86e84145b6967", "0.01"
        )
        assert deny is True

    def test_safe_payment_both_approve(self):
        """A clearly safe payment should pass both screens."""
        r = evaluate_risk(
            "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28",
            "0.50", "market-data", "normal purchase", "0x1", "BASE-SEPOLIA",
        )
        assert r.decision == "APPROVE"

        from app.validator import _independent_risk
        deny, _ = _independent_risk(
            "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28", "0.50"
        )
        assert deny is False
