"""Unit tests for the behavioral anomaly layer (circle/behavioral.py).

This exercises honest statistical signals — robust z-score outliers,
velocity bursts, novel counterparties, the degenerate constant-baseline
case — plus determinism and the persistence round-trip. No RNG, no
network: every input is explicit and every assertion is exact.
"""

from __future__ import annotations

from circle.behavioral import (
    BehavioralEngine,
    _robust_zscore,
    MIN_SAMPLES_FOR_ZSCORE,
    VELOCITY_MIN_COUNT,
    VELOCITY_WINDOW_S,
)

AGENT = "0x008ed50be2cd35f6333a37542a76a227e3b16acc"
PAYEE_A = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PAYEE_B = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _seed(engine, agent, amounts, payee=PAYEE_A, base_t=1000.0, step=120.0):
    """Record a history of amounts spaced far enough apart to avoid a
    velocity spike (step > VELOCITY_WINDOW_S)."""
    for i, amt in enumerate(amounts):
        engine.record(agent, payee, amt, "compute", at=base_t + i * step)


# ── robust z-score primitive ────────────────────────────────────────
def test_robust_zscore_needs_min_samples():
    assert _robust_zscore(10.0, [1.0, 2.0]) is None  # too few


def test_robust_zscore_flags_outlier():
    sample = [1.0, 1.1, 0.9, 1.05, 0.95, 1.02]
    z = _robust_zscore(50.0, sample)
    assert z is not None and z > 3.5


def test_robust_zscore_constant_sample_is_none():
    # All identical → MAD 0 and pstdev 0 → undefined, must not fabricate.
    assert _robust_zscore(9.0, [1.0] * 6) is None


# ── amount deviation (normal spread) ────────────────────────────────
def test_amount_deviation_normal_spread():
    eng = BehavioralEngine()
    _seed(eng, AGENT, [1.0, 1.1, 0.9, 1.05, 0.95, 1.02])
    sig = eng.assess(AGENT, PAYEE_A, 50.0, "compute", at=2000.0)
    assert "amount_deviation" in sig.signals
    assert sig.score > 0
    assert sig.details["amount_deviation"]["robust_z"] > 3.5


def test_amount_in_range_not_flagged():
    eng = BehavioralEngine()
    _seed(eng, AGENT, [1.0, 1.1, 0.9, 1.05, 0.95, 1.02])
    sig = eng.assess(AGENT, PAYEE_A, 1.03, "compute", at=2000.0)
    assert "amount_deviation" not in sig.signals


# ── amount deviation (degenerate constant baseline) ─────────────────
def test_constant_baseline_outlier_flagged():
    eng = BehavioralEngine()
    _seed(eng, AGENT, [0.5] * 6)  # perfectly constant history
    sig = eng.assess(AGENT, PAYEE_A, 500.0, "compute", at=2000.0)
    assert "amount_deviation" in sig.signals
    d = sig.details["amount_deviation"]
    assert d["baseline"] == "constant"
    assert d["ratio_to_baseline"] == 1000.0


def test_constant_baseline_same_value_not_flagged():
    eng = BehavioralEngine()
    _seed(eng, AGENT, [0.5] * 6)
    sig = eng.assess(AGENT, PAYEE_A, 0.5, "compute", at=2000.0)
    assert "amount_deviation" not in sig.signals


# ── velocity spike ──────────────────────────────────────────────────
def test_velocity_spike_detected():
    eng = BehavioralEngine()
    # VELOCITY_MIN_COUNT intents packed inside one window.
    t0 = 5000.0
    for i in range(VELOCITY_MIN_COUNT):
        eng.record(AGENT, PAYEE_A, 1.0, "compute", at=t0 + i)
    sig = eng.assess(AGENT, PAYEE_A, 1.0, "compute", at=t0 + VELOCITY_MIN_COUNT)
    assert "velocity_spike" in sig.signals
    assert sig.details["velocity_spike"]["count_in_window"] >= VELOCITY_MIN_COUNT


def test_no_velocity_spike_when_spread_out():
    eng = BehavioralEngine()
    _seed(eng, AGENT, [1.0] * VELOCITY_MIN_COUNT, step=VELOCITY_WINDOW_S + 10)
    sig = eng.assess(AGENT, PAYEE_A, 1.0, "compute", at=99999.0)
    assert "velocity_spike" not in sig.signals


# ── novel counterparty ──────────────────────────────────────────────
def test_new_counterparty_flagged():
    eng = BehavioralEngine()
    _seed(eng, AGENT, [1.0, 1.0, 1.0, 1.0, 1.0], payee=PAYEE_A)
    sig = eng.assess(AGENT, PAYEE_B, 1.0, "compute", at=2000.0)
    assert "new_counterparty" in sig.signals
    assert sig.confidence_delta < 0  # nudges toward STEP_UP


def test_known_counterparty_not_flagged():
    eng = BehavioralEngine()
    _seed(eng, AGENT, [1.0, 1.0, 1.0, 1.0, 1.0], payee=PAYEE_A)
    sig = eng.assess(AGENT, PAYEE_A, 1.0, "compute", at=2000.0)
    assert "new_counterparty" not in sig.signals


# ── cold start ──────────────────────────────────────────────────────
def test_cold_start_no_signals():
    eng = BehavioralEngine()
    sig = eng.assess(AGENT, PAYEE_A, 100.0, "compute", at=1000.0)
    assert sig.signals == []
    assert sig.score == 0
    assert "history" in sig.details


# ── determinism ─────────────────────────────────────────────────────
def test_assess_is_deterministic():
    eng = BehavioralEngine()
    _seed(eng, AGENT, [1.0, 1.1, 0.9, 1.05, 0.95, 1.02])
    a = eng.assess(AGENT, PAYEE_A, 50.0, "compute", at=2000.0)
    b = eng.assess(AGENT, PAYEE_A, 50.0, "compute", at=2000.0)
    assert a.score == b.score
    assert a.signals == b.signals
    assert a.details == b.details


def test_assess_does_not_mutate_history():
    eng = BehavioralEngine()
    _seed(eng, AGENT, [1.0, 1.1, 0.9, 1.05, 0.95, 1.02])
    before = eng.agent_stats(AGENT)["observations"]
    eng.assess(AGENT, PAYEE_B, 999.0, "compute", at=2000.0)
    after = eng.agent_stats(AGENT)["observations"]
    assert before == after  # read path never writes


# ── persistence round-trip ──────────────────────────────────────────
def test_state_round_trip():
    eng = BehavioralEngine()
    _seed(eng, AGENT, [1.0, 2.0, 3.0], payee=PAYEE_A)
    eng.record(AGENT, PAYEE_B, 4.0, "storage", at=9000.0)
    state = eng.to_state()

    restored = BehavioralEngine()
    restored.load_state(state)

    assert restored.agent_stats(AGENT)["observations"] == 4
    assert restored.agent_stats(AGENT)["distinct_payees"] == 2
    # A known payee stays known after restore.
    sig = restored.assess(AGENT, PAYEE_A, 2.0, "compute", at=9500.0)
    assert "new_counterparty" not in sig.signals


def test_history_capped_at_max():
    eng = BehavioralEngine(max_history=10)
    for i in range(25):
        eng.record(AGENT, PAYEE_A, float(i), "compute", at=1000.0 + i * 200)
    assert eng.agent_stats(AGENT)["observations"] == 10


def test_agent_stats_empty():
    eng = BehavioralEngine()
    stats = eng.agent_stats("0xunknown")
    assert stats["observations"] == 0
    assert stats["distinct_payees"] == 0
    assert stats["median_amount"] is None
