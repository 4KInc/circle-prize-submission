"""Tests for enforcement loop (A1-A4)."""

import time
from circle.enforcement import EnforcementEngine


def _make_engine(**kwargs):
    return EnforcementEngine(
        replay_window_seconds=kwargs.get("replay_window_seconds", 60),
        breaker_threshold=kwargs.get("breaker_threshold", 3),
        breaker_window_seconds=kwargs.get("breaker_window_seconds", 60),
        breaker_suspend_after=kwargs.get("breaker_suspend_after", 6),
    )


def test_a1_replay_detection():
    """A1: Repeat of denied intent short-circuits to prior DENY without re-scoring."""
    engine = _make_engine()
    intent = {"payee": "0xdead", "amount": "100", "service": "test", "reason": "bad"}

    # No replay before recording
    assert engine.check_replay(**intent) is None

    # Record a denial
    engine.record_denial(
        **intent, decision="DENY", score=90, band="CRITICAL",
        confidence=0.95, signals=["sanctioned"], rationale="OFAC hit",
    )

    # Now replay should be detected
    replay = engine.check_replay(**intent)
    assert replay is not None
    assert replay.decision == "DENY"
    assert replay.score == 90
    assert replay.replay_count == 1

    # Second replay increments count
    replay2 = engine.check_replay(**intent)
    assert replay2.replay_count == 2


def test_a1_different_intent_not_replayed():
    """Different intents are not treated as replays."""
    engine = _make_engine()
    engine.record_denial(
        payee="0xdead", amount="100", service="test", reason="bad",
        decision="DENY", score=90, band="CRITICAL",
        confidence=0.95, signals=["sanctioned"], rationale="OFAC hit",
    )

    # Different payee
    assert engine.check_replay("0xbeef", "100", "test", "bad") is None
    # Different amount
    assert engine.check_replay("0xdead", "200", "test", "bad") is None


def test_a2_replay_no_step_up():
    """A2: Replays should not trigger STEP_UP or full charge."""
    engine = _make_engine()
    intent = {"payee": "0xdead", "amount": "100", "service": "test", "reason": "bad"}

    engine.record_denial(
        **intent, decision="DENY", score=90, band="CRITICAL",
        confidence=0.95, signals=["sanctioned"], rationale="OFAC hit",
    )

    replay = engine.check_replay(**intent)
    # The replay record is the cached denial — no STEP_UP, no re-scoring
    assert replay.decision == "DENY"
    assert "STEP_UP" not in replay.decision


def test_a3_circuit_breaker_throttle():
    """A3: After K denials in a window, session is throttled."""
    engine = _make_engine(breaker_threshold=3, breaker_suspend_after=6)
    intent = {"payee": "0xdead", "amount": "100", "service": "test", "reason": "bad"}

    for i in range(3):
        engine.record_denial(
            **intent, decision="DENY", score=90, band="CRITICAL",
            confidence=0.95, signals=["sanctioned"], rationale="OFAC hit",
            session_id="test-session",
        )

    breaker = engine.check_breaker("test-session")
    assert breaker["status"] == "session_throttled"


def test_a3_circuit_breaker_suspend():
    """A3: After more denials, session is suspended."""
    engine = _make_engine(breaker_threshold=3, breaker_suspend_after=6)
    intent = {"payee": "0xdead", "amount": "100", "service": "test", "reason": "bad"}

    for i in range(6):
        engine.record_denial(
            **intent, decision="DENY", score=90, band="CRITICAL",
            confidence=0.95, signals=["sanctioned"], rationale="OFAC hit",
            session_id="test-session",
        )

    breaker = engine.check_breaker("test-session")
    assert breaker["status"] == "session_suspended"


def test_a3_different_sessions_independent():
    """Distinct intents from other sessions are unaffected."""
    engine = _make_engine(breaker_threshold=3)
    intent = {"payee": "0xdead", "amount": "100", "service": "test", "reason": "bad"}

    for i in range(5):
        engine.record_denial(
            **intent, decision="DENY", score=90, band="CRITICAL",
            confidence=0.95, signals=["sanctioned"], rationale="OFAC hit",
            session_id="bad-session",
        )

    # Different session should be unaffected
    breaker = engine.check_breaker("good-session")
    assert breaker["status"] == "active"


def test_a4_enforcement_state_returned():
    """A4: Enforcement state is always present in breaker check."""
    engine = _make_engine()
    breaker = engine.check_breaker("any-session")
    assert "status" in breaker
    assert "denial_count" in breaker
    assert "breaker_threshold" in breaker
    assert breaker["status"] == "active"


def test_session_reset():
    """Session reset clears enforcement state."""
    engine = _make_engine(breaker_threshold=2)
    intent = {"payee": "0xdead", "amount": "100", "service": "test", "reason": "bad"}

    for i in range(3):
        engine.record_denial(
            **intent, decision="DENY", score=90, band="CRITICAL",
            confidence=0.95, signals=["sanctioned"], rationale="OFAC hit",
            session_id="reset-test",
        )

    assert engine.check_breaker("reset-test")["status"] == "session_throttled"
    engine.reset_session("reset-test")
    assert engine.check_breaker("reset-test")["status"] == "active"
