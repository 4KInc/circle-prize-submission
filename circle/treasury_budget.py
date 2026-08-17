"""Treasury spend guard for autonomous evidence purchases.

The STEP_UP settlement path is reachable from public, unauthenticated
endpoints — that is deliberate, because a judge or an evaluator must be able
to exercise the autonomous loop without credentials. The consequence is that
the treasury is exposed to repeated invocation, and the dynamic evidence fee
(`max($0.02, min(amount * 0.1%, $5.00))`) bounds a *single* purchase without
bounding a *sequence* of them.

This module supplies the missing bound. Two independent limits:

  1. Per-call ceiling — no single evidence purchase may exceed
     ``EVIDENCE_MAX_PER_CALL_USDC`` regardless of what the fee formula
     produces for a large intent.
  2. Daily budget — cumulative evidence spend in a UTC day may not exceed
     ``EVIDENCE_DAILY_BUDGET_USDC``.

When a limit is reached the purchase is refused. The caller must treat that
exactly as it treats an unavailable validator: **fail closed**. Refusing to
spend must never be read as approval.

Known limitation, stated rather than implied: counters are per-process and
in-memory, so they reset on restart and are tracked independently by each
Cloud Run instance. The effective bound is therefore
``instances x EVIDENCE_DAILY_BUDGET_USDC`` per day, not a global ceiling.
The per-call limit has no such weakness. A durable global budget needs
shared state and is tracked as follow-up work.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime


def _env_float(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return v if v >= 0 else default


# Defaults are deliberately tight. The demo spends $0.02 per purchase, so a
# $1.00 daily budget permits 50 autonomous evidence purchases per instance
# per day — ample for evaluation, far below a treasury-draining sequence.
EVIDENCE_MAX_PER_CALL_USDC = _env_float("EVIDENCE_MAX_PER_CALL_USDC", 0.25)
EVIDENCE_DAILY_BUDGET_USDC = _env_float("EVIDENCE_DAILY_BUDGET_USDC", 1.00)


@dataclass(frozen=True)
class BudgetDecision:
    """Outcome of a spend request."""

    allowed: bool
    amount: float          # amount authorised (clamped); 0.0 when refused
    reason: str            # machine-readable code
    detail: str            # human-readable explanation
    spent_today: float
    daily_budget: float

    @property
    def remaining(self) -> float:
        return max(0.0, self.daily_budget - self.spent_today)


class _TreasuryBudget:
    """Thread-safe, per-process evidence spend ledger."""

    # USDC has 6 decimals, so spend is tracked in integer micro-USDC.
    # Accumulating floats drifts (0.02 x 50 = 1.0000000000000002) and would
    # silently make the budget off-by-one against its stated value.
    _MICRO = 1_000_000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day: str = ""
        self._spent_micro: int = 0

    @property
    def _spent(self) -> float:
        return self._spent_micro / self._MICRO

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _roll(self) -> None:
        """Reset the ledger when the UTC day changes. Caller holds the lock."""
        today = self._today()
        if self._day != today:
            self._day = today
            self._spent_micro = 0

    def check_and_reserve(self, requested: float) -> BudgetDecision:
        """Authorise an evidence purchase, reserving it against the budget.

        Reservation happens atomically with the check so concurrent callers
        cannot both pass on the same remaining headroom.
        """
        with self._lock:
            self._roll()

            if requested <= 0:
                return BudgetDecision(
                    False, 0.0, "invalid_amount",
                    f"requested amount ${requested:.4f} is not positive",
                    self._spent, EVIDENCE_DAILY_BUDGET_USDC,
                )

            if requested > EVIDENCE_MAX_PER_CALL_USDC:
                return BudgetDecision(
                    False, 0.0, "per_call_ceiling",
                    f"${requested:.4f} exceeds per-call ceiling of "
                    f"${EVIDENCE_MAX_PER_CALL_USDC:.2f}",
                    self._spent, EVIDENCE_DAILY_BUDGET_USDC,
                )

            requested_micro = round(requested * self._MICRO)
            budget_micro = round(EVIDENCE_DAILY_BUDGET_USDC * self._MICRO)
            if self._spent_micro + requested_micro > budget_micro:
                return BudgetDecision(
                    False, 0.0, "daily_budget_exhausted",
                    f"${requested:.4f} would exceed the daily evidence budget "
                    f"of ${EVIDENCE_DAILY_BUDGET_USDC:.2f} "
                    f"(${self._spent:.4f} already spent today)",
                    self._spent, EVIDENCE_DAILY_BUDGET_USDC,
                )

            self._spent_micro += requested_micro
            return BudgetDecision(
                True, requested, "authorised",
                f"authorised ${requested:.4f}; "
                f"${self._spent:.4f}/${EVIDENCE_DAILY_BUDGET_USDC:.2f} spent today",
                self._spent, EVIDENCE_DAILY_BUDGET_USDC,
            )

    def release(self, amount: float) -> None:
        """Return a reservation when the transfer did not actually settle."""
        with self._lock:
            self._roll()
            self._spent_micro = max(0, self._spent_micro - round(amount * self._MICRO))

    def status(self) -> dict:
        with self._lock:
            self._roll()
            return {
                "day_utc": self._day,
                "spent_today_usdc": round(self._spent, 6),
                "daily_budget_usdc": EVIDENCE_DAILY_BUDGET_USDC,
                "remaining_usdc": round(
                    max(0.0, EVIDENCE_DAILY_BUDGET_USDC - self._spent), 6
                ),
                "per_call_ceiling_usdc": EVIDENCE_MAX_PER_CALL_USDC,
                "scope": "per-process, in-memory; resets on restart",
            }

    def _reset_for_tests(self) -> None:
        with self._lock:
            self._day = ""
            self._spent_micro = 0


_budget = _TreasuryBudget()


def check_and_reserve(requested: float) -> BudgetDecision:
    """Authorise and reserve an autonomous evidence purchase."""
    return _budget.check_and_reserve(requested)


def release(amount: float) -> None:
    """Release a reservation whose transfer failed."""
    _budget.release(amount)


def status() -> dict:
    """Current budget state, safe to expose publicly."""
    return _budget.status()
