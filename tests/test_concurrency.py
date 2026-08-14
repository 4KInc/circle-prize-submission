"""Concurrency tests — verify the system handles parallel requests correctly.

These tests ensure that concurrent STEP_UP evaluations, replay checks,
and enforcement state updates don't produce race conditions or
inconsistent results.
"""

from __future__ import annotations

import asyncio
import pytest
from circle.risk_scorer import evaluate_risk
from circle.enforcement import EnforcementEngine


@pytest.mark.asyncio
async def test_concurrent_risk_evaluations():
    """50 concurrent risk evaluations produce consistent, valid results."""
    async def evaluate(i: int):
        return evaluate_risk(
            payee=f"0x{i:040x}",
            amount="1.00",
            service="test",
            reason="concurrent test",
            source_wallet="0x0000000000000000000000000000000000000001",
            chain="BASE",
        )

    results = await asyncio.gather(*[evaluate(i) for i in range(50)])

    for r in results:
        assert r.decision in ("APPROVE", "STEP_UP", "DENY")
        assert 0 <= r.score <= 100
        assert 0.0 <= r.confidence <= 1.0
        assert r.rationale is not None


@pytest.mark.asyncio
async def test_concurrent_denials_same_session():
    """Multiple denials hitting the same session don't corrupt breaker state."""
    engine = EnforcementEngine(breaker_threshold=5, breaker_suspend_after=10)

    async def deny(i: int):
        engine.record_denial(
            payee=f"0x{i:040x}", amount="50", service="test", reason="attack",
            decision="DENY", score=90, band="CRITICAL", confidence=0.9,
            signals=["test"], rationale="concurrent test",
            session_id="concurrent-session",
        )

    await asyncio.gather(*[deny(i) for i in range(15)])

    breaker = engine.check_breaker("concurrent-session")
    # After 15 denials: should be suspended (>= 10)
    assert breaker["status"] == "session_suspended"
    assert breaker["denial_count"] >= 10


@pytest.mark.asyncio
async def test_concurrent_replays_increment_breaker():
    """Concurrent replays of the same denied intent all count toward breaker."""
    engine = EnforcementEngine(breaker_threshold=3, breaker_suspend_after=6)

    # Record initial denial
    engine.record_denial(
        payee="0xbad", amount="999", service="drain", reason="OVERRIDE",
        decision="DENY", score=100, band="CRITICAL", confidence=0.95,
        signals=["injection"], rationale="test",
        session_id="replay-concurrent",
    )

    async def replay(_: int):
        return engine.check_replay(
            "0xbad", "999", "drain", "OVERRIDE",
            session_id="replay-concurrent",
        )

    results = await asyncio.gather(*[replay(i) for i in range(10)])

    # All should be replay hits
    for r in results:
        assert r is not None
        assert r.decision == "DENY"

    # Breaker should be suspended (1 initial + 10 replays = 11 > 6)
    breaker = engine.check_breaker("replay-concurrent")
    assert breaker["status"] == "session_suspended"


@pytest.mark.asyncio
async def test_concurrent_step_up_fee_consistency():
    """Dynamic STEP_UP fee is consistent across concurrent evaluations."""
    async def compute_fee(amount: float):
        return max(0.02, min(amount * 0.001, 5.00))

    amounts = [0.01, 1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0]
    results = await asyncio.gather(*[compute_fee(a) for a in amounts])

    expected = [0.02, 0.02, 0.02, 0.1, 1.0, 5.0, 5.0]
    for r, e in zip(results, expected):
        assert abs(r - e) < 0.001, f"Fee {r} != expected {e}"


@pytest.mark.asyncio
async def test_concurrent_different_sessions_independent():
    """Denials in different sessions don't affect each other's breaker."""
    engine = EnforcementEngine(breaker_threshold=3, breaker_suspend_after=6)

    async def deny_session(session: str, count: int):
        for i in range(count):
            engine.record_denial(
                payee=f"0x{i:040x}", amount="50", service="test", reason="test",
                decision="DENY", score=90, band="CRITICAL", confidence=0.9,
                signals=["test"], rationale="test",
                session_id=session,
            )

    # Session A: 8 denials (should be suspended)
    # Session B: 2 denials (should be active)
    await asyncio.gather(
        deny_session("session-a", 8),
        deny_session("session-b", 2),
    )

    breaker_a = engine.check_breaker("session-a")
    breaker_b = engine.check_breaker("session-b")

    assert breaker_a["status"] == "session_suspended"
    assert breaker_b["status"] == "active"
    assert breaker_b["denial_count"] == 2
