"""Enforcement loop: replay detection, circuit breaker, session management.

P0 — Feedback A: all enforcement is synchronous, deterministic, in-path.
No carrier dependency. No LLM.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field


def _intent_digest(payee: str, amount: str, service: str, reason: str) -> str:
    """RFC 8785-style canonical digest of a payment intent."""
    canonical = json.dumps(
        {"payee": payee.lower(), "amount": amount, "service": service, "reason": reason},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class DenialRecord:
    """Cached denial for replay detection."""
    digest: str
    decision: str
    score: int
    band: str
    confidence: float
    signals: list[str]
    rationale: str
    denied_at: float
    replay_count: int = 0


@dataclass
class SessionState:
    """Per-session enforcement state."""
    session_id: str
    denial_count: int = 0
    denial_window_start: float = 0.0
    throttled: bool = False
    suspended: bool = False
    last_denial_at: float = 0.0


class EnforcementEngine:
    """Decision memory + circuit breaker for the payment authorization path.

    A1: Replay detection — repeat of a denied intent short-circuits to prior DENY.
    A2: No re-charge for replays — free, no STEP_UP.
    A3: Circuit breaker — after K denials in a window, throttle then suspend.
    A4: Enforcement state returned synchronously in every response.
    """

    def __init__(
        self,
        replay_window_seconds: int = 3600,
        breaker_threshold: int = 5,
        breaker_window_seconds: int = 300,
        breaker_suspend_after: int = 10,
    ):
        self.replay_window = replay_window_seconds
        self.breaker_threshold = breaker_threshold
        self.breaker_window = breaker_window_seconds
        self.breaker_suspend_after = breaker_suspend_after

        # digest -> DenialRecord
        self._denial_cache: dict[str, DenialRecord] = {}
        # session_id -> SessionState
        self._sessions: dict[str, SessionState] = {}

    def _get_session(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id=session_id)
        return self._sessions[session_id]

    def _evict_stale(self) -> None:
        """Remove expired denial records."""
        now = time.time()
        stale = [d for d, r in self._denial_cache.items()
                 if now - r.denied_at > self.replay_window]
        for d in stale:
            del self._denial_cache[d]

    def check_replay(
        self, payee: str, amount: str, service: str, reason: str,
        session_id: str = "default",
    ) -> DenialRecord | None:
        """A1: Check if this intent was already denied within the replay window.

        Replays are free (A2: no re-scoring, no re-charge) but they DO
        count toward the circuit breaker. If an agent hammers the same
        denied intent repeatedly, the session gets throttled then suspended.
        """
        self._evict_stale()
        digest = _intent_digest(payee, amount, service, reason)
        record = self._denial_cache.get(digest)
        if record and time.time() - record.denied_at <= self.replay_window:
            record.replay_count += 1
            # Replays count toward circuit breaker — repeated hammering is suspicious
            session = self._get_session(session_id)
            now = time.time()
            if now - session.denial_window_start > self.breaker_window:
                session.denial_count = 0
                session.denial_window_start = now
            session.denial_count += 1
            session.last_denial_at = now
            if session.denial_count >= self.breaker_suspend_after:
                session.suspended = True
            elif session.denial_count >= self.breaker_threshold:
                session.throttled = True
            return record
        return None

    def record_denial(
        self,
        payee: str, amount: str, service: str, reason: str,
        decision: str, score: int, band: str, confidence: float,
        signals: list[str], rationale: str,
        session_id: str = "default",
    ) -> None:
        """Cache a denial for future replay detection + update circuit breaker."""
        digest = _intent_digest(payee, amount, service, reason)
        self._denial_cache[digest] = DenialRecord(
            digest=digest,
            decision=decision,
            score=score,
            band=band,
            confidence=confidence,
            signals=signals,
            rationale=rationale,
            denied_at=time.time(),
        )
        # Update circuit breaker state
        session = self._get_session(session_id)
        now = time.time()
        if now - session.denial_window_start > self.breaker_window:
            session.denial_count = 0
            session.denial_window_start = now
        session.denial_count += 1
        session.last_denial_at = now

        if session.denial_count >= self.breaker_suspend_after:
            session.suspended = True
        elif session.denial_count >= self.breaker_threshold:
            session.throttled = True

    def check_breaker(self, session_id: str = "default") -> dict:
        """A3/A4: Return enforcement state for this session."""
        session = self._get_session(session_id)
        now = time.time()

        # Reset window if expired
        if now - session.denial_window_start > self.breaker_window:
            session.denial_count = 0
            session.throttled = False
            session.suspended = False
            session.denial_window_start = now

        status = "active"
        if session.suspended:
            status = "session_suspended"
        elif session.throttled:
            status = "session_throttled"

        return {
            "status": status,
            "denial_count": session.denial_count,
            "breaker_threshold": self.breaker_threshold,
            "suspend_threshold": self.breaker_suspend_after,
            "window_seconds": self.breaker_window,
        }

    def reset_session(self, session_id: str = "default") -> None:
        """Reset a session's enforcement state."""
        if session_id in self._sessions:
            del self._sessions[session_id]


# Module-level singleton
_engine: EnforcementEngine | None = None


def get_engine() -> EnforcementEngine:
    global _engine
    if _engine is None:
        _engine = EnforcementEngine()
    return _engine
