"""The treasury spend guard bounds a *sequence* of evidence purchases.

The dynamic fee formula bounds one purchase. It does not bound repeated
invocation, and the STEP_UP settlement path is reachable from public,
unauthenticated endpoints. These tests pin the bound, and — more importantly
— pin that a refusal is never an approval.
"""

from __future__ import annotations

import pytest

import circle.treasury_budget as tb
from circle.treasury_budget import check_and_reserve, release, status


@pytest.fixture(autouse=True)
def _reset():
    tb._budget._reset_for_tests()
    yield
    tb._budget._reset_for_tests()


class TestPerCallCeiling:
    def test_normal_evidence_fee_allowed(self):
        d = check_and_reserve(0.02)
        assert d.allowed is True
        assert d.amount == 0.02

    def test_above_ceiling_refused(self):
        """The fee formula tops out at $5.00; the ceiling must catch that."""
        d = check_and_reserve(5.00)
        assert d.allowed is False
        assert d.reason == "per_call_ceiling"

    def test_ceiling_is_below_formula_max(self):
        """A single call must not be able to drain a small treasury."""
        assert tb.EVIDENCE_MAX_PER_CALL_USDC < 5.00

    def test_zero_and_negative_refused(self):
        assert check_and_reserve(0).allowed is False
        assert check_and_reserve(-1).allowed is False


class TestDailyBudget:
    def test_budget_exhausts_after_repeated_calls(self):
        """The drain scenario: hammer the public endpoint."""
        allowed = sum(1 for _ in range(500) if check_and_reserve(0.02).allowed)
        assert allowed == int(tb.EVIDENCE_DAILY_BUDGET_USDC / 0.02)

    def test_refusal_reason_is_budget(self):
        while check_and_reserve(0.02).allowed:
            pass
        assert check_and_reserve(0.02).reason == "daily_budget_exhausted"

    def test_total_spend_never_exceeds_budget(self):
        for _ in range(500):
            check_and_reserve(0.02)
        assert status()["spent_today_usdc"] <= tb.EVIDENCE_DAILY_BUDGET_USDC

    def test_bounded_loss_is_small_against_treasury(self):
        """Per-instance daily exposure must stay well under the treasury."""
        assert tb.EVIDENCE_DAILY_BUDGET_USDC <= 1.00

    def test_reservation_is_atomic(self):
        """Concurrent callers must not both pass on the same headroom."""
        import threading
        results = []
        barrier = threading.Barrier(20)

        def worker():
            barrier.wait()
            results.append(check_and_reserve(0.02).allowed)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sum(results) * 0.02 <= tb.EVIDENCE_DAILY_BUDGET_USDC
        assert status()["spent_today_usdc"] <= tb.EVIDENCE_DAILY_BUDGET_USDC


class TestRelease:
    def test_failed_transfer_returns_headroom(self):
        check_and_reserve(0.02)
        before = status()["spent_today_usdc"]
        release(0.02)
        assert status()["spent_today_usdc"] == pytest.approx(before - 0.02)

    def test_release_never_goes_negative(self):
        release(99.0)
        assert status()["spent_today_usdc"] == 0.0


class TestStatus:
    def test_status_is_publicly_safe(self):
        s = status()
        for k in ("spent_today_usdc", "daily_budget_usdc", "remaining_usdc",
                  "per_call_ceiling_usdc", "scope"):
            assert k in s

    def test_status_discloses_per_process_scope(self):
        """The known limitation must be stated, not implied."""
        assert "per-process" in status()["scope"]

    def test_remaining_tracks_spend(self):
        check_and_reserve(0.02)
        s = status()
        assert s["remaining_usdc"] == pytest.approx(s["daily_budget_usdc"] - 0.02)
