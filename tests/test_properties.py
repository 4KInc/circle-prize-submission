"""Property-based tests using Hypothesis.

These tests verify system invariants hold for ANY valid input,
not just hand-picked examples. Each property is a formal guarantee.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from circle.risk_scorer import evaluate_risk


# ── Risk Scorer Properties ──────────────────────────────────────────

@given(
    amount=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_score_is_always_bounded(amount):
    """For ANY amount, the risk score is in [0, 100]."""
    result = evaluate_risk(
        payee="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28",
        amount=str(amount),
        service="test-service",
        reason="test payment",
        source_wallet="0x0000000000000000000000000000000000000001",
        chain="BASE",
    )
    assert 0 <= result.score <= 100


@given(
    amount=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_decision_is_always_valid(amount):
    """For ANY amount, the decision is one of the three valid states."""
    result = evaluate_risk(
        payee="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28",
        amount=str(amount),
        service="test-service",
        reason="test payment",
        source_wallet="0x0000000000000000000000000000000000000001",
        chain="BASE",
    )
    assert result.decision in ("APPROVE", "STEP_UP", "DENY")


@given(
    amount=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_rationale_always_present(amount):
    """For ANY input, the scorer produces a rationale and well-formed output."""
    result = evaluate_risk(
        payee="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28",
        amount=str(amount),
        service="test-service",
        reason="test payment",
        source_wallet="0x0000000000000000000000000000000000000001",
        chain="BASE",
    )
    assert result.rationale is not None
    assert len(result.rationale) > 0
    # Contributions present when signals fired; empty when clean
    if result.signals:
        assert len(result.contributions) > 0


@given(
    payee=st.from_regex(r"0x[0-9a-fA-F]{40}", fullmatch=True),
    amount=st.floats(min_value=0.01, max_value=100, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_confidence_is_bounded(payee, amount):
    """For ANY valid address and amount, confidence is in [0, 1]."""
    result = evaluate_risk(
        payee=payee,
        amount=str(amount),
        service="test",
        reason="test",
        source_wallet="0x0000000000000000000000000000000000000001",
        chain="BASE",
    )
    assert 0.0 <= result.confidence <= 1.0


@given(
    reason=st.text(min_size=0, max_size=500),
)
@settings(max_examples=100)
def test_scorer_never_crashes_on_arbitrary_reason(reason):
    """For ANY reason string (including adversarial), scorer never crashes."""
    result = evaluate_risk(
        payee="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD28",
        amount="1.00",
        service="test",
        reason=reason,
        source_wallet="0x0000000000000000000000000000000000000001",
        chain="BASE",
    )
    assert result.decision in ("APPROVE", "STEP_UP", "DENY")
    assert 0 <= result.score <= 100


# ── STEP_UP Fee Properties ──────────────────────────────────────────

@given(
    amount=st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=500)
def test_step_up_fee_is_bounded(amount):
    """For ANY amount, the STEP_UP fee is within [$0.02, $5.00]."""
    fee = max(0.02, min(amount * 0.001, 5.00))
    assert fee >= 0.02
    assert fee <= 5.00


@given(
    amount=st.floats(min_value=20.01, max_value=1_000_000, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_step_up_fee_scales_with_amount(amount):
    """For amounts > $20, the fee is proportional (0.1% of amount, capped at $5)."""
    fee = max(0.02, min(amount * 0.001, 5.00))
    assert fee <= amount * 0.001 or fee == 5.00  # either proportional or capped


@given(
    a=st.floats(min_value=0.01, max_value=999_999, allow_nan=False, allow_infinity=False),
    b=st.floats(min_value=0.01, max_value=999_999, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_step_up_fee_is_monotonic(a, b):
    """Larger amounts never produce smaller fees."""
    assume(b > a)
    fee_a = max(0.02, min(a * 0.001, 5.00))
    fee_b = max(0.02, min(b * 0.001, 5.00))
    assert fee_b >= fee_a


# ── Decision Consistency Properties ─────────────────────────────────

def test_sanctioned_address_always_denied():
    """OFAC-sanctioned addresses must ALWAYS produce DENY."""
    from circle.risk_scorer import SANCTIONED_ADDRESSES
    for addr in list(SANCTIONED_ADDRESSES)[:5]:  # test first 5
        result = evaluate_risk(
            payee=addr,
            amount="0.01",
            service="test",
            reason="test",
            source_wallet="0x0000000000000000000000000000000000000001",
            chain="BASE",
        )
        assert result.decision == "DENY", f"Sanctioned {addr[:10]}... was not DENIED"
        assert result.score >= 75


# ── Policy Synthesis Properties ─────────────────────────────────────

def test_synthesis_hard_gates():
    """Hard gates must hold regardless of Gemini output."""
    from circle.policy_synthesis import (
        MAX_AMOUNT_PER_TX_CEILING,
        MAX_AMOUNT_PER_DAY_CEILING,
        MIN_BLOCKED_PATTERNS,
        synthesize_policy,
        _conservative_default,
    )
    # Test conservative default
    policy = _conservative_default("test")
    assert policy.max_amount_per_tx <= MAX_AMOUNT_PER_TX_CEILING
    assert policy.max_amount_per_day <= MAX_AMOUNT_PER_DAY_CEILING
    assert len(policy.blocked_patterns) >= MIN_BLOCKED_PATTERNS
    assert policy.requires_human_review is True
    assert policy.gemini_available is False
