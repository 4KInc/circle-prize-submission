"""Behavioral anomaly layer — per-agent transaction history + statistics.

This is honest statistical behavioral analysis, NOT machine learning. It
keeps a rolling history of the payment intents each agent (source wallet)
has been evaluated for, and derives anomaly signals from real properties
of that history:

  - amount_deviation  — the amount is a robust-z-score outlier versus the
                        agent's OWN historical amounts (median + MAD, which
                        resist a few large values skewing the baseline).
  - velocity_spike    — an unusual burst of intents inside a short window.
  - new_counterparty  — a payee this agent has never transacted with before
                        (only meaningful once the agent has some history).

Every signal is deterministic given the history state and inputs — there
is no RNG. The engine separates READ (assess, used during scoring) from
WRITE (record, called explicitly by a caller after a real decision) so
that pre-flight/quick-check scoring never pollutes the behavioral history.

State is JSON-serializable and can be persisted to (and restored from)
GCS via app.storage, so history survives Cloud Run restarts — which is
what makes the "continuous autonomous operation" claim real rather than
resetting on every cold start.
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger("circle.behavioral")

HISTORY_STATE_PATH = "behavioral/agent_history.json"

# Tunables (declared, auditable — not magic numbers buried in code).
MAX_HISTORY_PER_AGENT = 500     # cap memory / state size
MIN_SAMPLES_FOR_ZSCORE = 5      # need a baseline before calling outliers
ZSCORE_THRESHOLD = 3.5          # robust-z beyond this is anomalous
VELOCITY_WINDOW_S = 60.0        # trailing window for burst detection
VELOCITY_MIN_COUNT = 5          # this many intents in-window is a spike


@dataclass
class Observation:
    at: float          # epoch seconds
    amount: float
    payee: str         # lowercased
    service: str

    def to_dict(self) -> dict:
        return {"at": self.at, "amount": self.amount, "payee": self.payee, "service": self.service}

    @classmethod
    def from_dict(cls, d: dict) -> "Observation":
        return cls(
            at=float(d.get("at", 0.0)),
            amount=float(d.get("amount", 0.0)),
            payee=str(d.get("payee", "")).lower(),
            service=str(d.get("service", "")),
        )


@dataclass
class BehavioralSignal:
    """The behavioral layer's contribution to a risk assessment."""
    score: int = 0
    confidence_delta: float = 0.0
    signals: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


def _robust_zscore(value: float, sample: list[float]) -> float | None:
    """Median/MAD-based z-score. Returns None if MAD is degenerate."""
    if len(sample) < MIN_SAMPLES_FOR_ZSCORE:
        return None
    med = statistics.median(sample)
    abs_dev = [abs(x - med) for x in sample]
    mad = statistics.median(abs_dev)
    if mad == 0:
        # Fall back to stdev when MAD collapses (many identical values).
        try:
            sd = statistics.pstdev(sample)
        except statistics.StatisticsError:
            return None
        if sd == 0:
            return None
        return (value - med) / sd
    # 1.4826 scales MAD to be consistent with stdev for normal data.
    return (value - med) / (1.4826 * mad)


class BehavioralEngine:
    """Thread-safe per-agent history + anomaly assessment."""

    def __init__(self, max_history: int = MAX_HISTORY_PER_AGENT):
        self._max = max_history
        self._hist: dict[str, list[Observation]] = {}
        self._payees: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    # ── Read path (used during scoring, no mutation) ────────────────
    def assess(self, source_wallet: str, payee: str, amount: float,
               service: str, at: float | None = None) -> BehavioralSignal:
        agent = (source_wallet or "").lower()
        p = (payee or "").lower()
        now = at if at is not None else time.time()

        with self._lock:
            hist = list(self._hist.get(agent, []))
            seen_payees = set(self._payees.get(agent, set()))

        sig = BehavioralSignal()
        if not hist:
            # Cold start for this agent — nothing to compare against yet.
            sig.details["history"] = "no prior observations for this agent"
            return sig

        # 1. Amount deviation vs the agent's own history.
        amounts = [o.amount for o in hist]
        median_amt = statistics.median(amounts)
        z = _robust_zscore(amount, amounts)
        if z is not None and z > ZSCORE_THRESHOLD:
            # Normal case: enough spread to compute a robust z-score.
            sig.signals.append("amount_deviation")
            sig.score += min(int((z - ZSCORE_THRESHOLD) * 8) + 10, 30)
            sig.details["amount_deviation"] = {
                "robust_z": round(z, 2),
                "median": round(median_amt, 4),
                "samples": len(amounts),
            }
        elif (z is None and len(amounts) >= MIN_SAMPLES_FOR_ZSCORE
              and statistics.pstdev(amounts) == 0):
            # Degenerate case: the agent's amounts are effectively constant,
            # so a z-score is undefined. We do NOT fabricate one — instead we
            # apply an honest relative-deviation rule: a value materially
            # different from a constant baseline is anomalous.
            if abs(amount - median_amt) > max(median_amt, 0.01):
                ratio = amount / median_amt if median_amt > 0 else float("inf")
                sig.signals.append("amount_deviation")
                sig.score += min(int(abs(ratio - 1) * 5) + 10, 30) if median_amt > 0 else 20
                sig.details["amount_deviation"] = {
                    "baseline": "constant",
                    "median": round(median_amt, 4),
                    "ratio_to_baseline": round(ratio, 2) if median_amt > 0 else None,
                    "samples": len(amounts),
                }

        # 2. Velocity spike — burst of intents in a short trailing window
        window = [o for o in hist if 0 <= now - o.at <= VELOCITY_WINDOW_S]
        if len(window) >= VELOCITY_MIN_COUNT:
            sig.signals.append("velocity_spike")
            sig.score += min(len(window) * 3, 25)
            sig.details["velocity_spike"] = {
                "count_in_window": len(window),
                "window_seconds": VELOCITY_WINDOW_S,
            }

        # 3. Novel counterparty for an established agent
        if p and p not in seen_payees:
            sig.signals.append("new_counterparty")
            sig.score += 10
            sig.confidence_delta -= 0.10  # nudge toward STEP_UP, not a hard block
            sig.details["new_counterparty"] = "first time this agent pays this payee"

        return sig

    # ── Write path (explicit, after a real decision) ────────────────
    def record(self, source_wallet: str, payee: str, amount: float,
               service: str, at: float | None = None) -> None:
        agent = (source_wallet or "").lower()
        p = (payee or "").lower()
        obs = Observation(at=at if at is not None else time.time(),
                          amount=float(amount), payee=p, service=service)
        with self._lock:
            lst = self._hist.setdefault(agent, [])
            lst.append(obs)
            if len(lst) > self._max:
                del lst[: len(lst) - self._max]
            self._payees.setdefault(agent, set()).add(p)

    def agent_stats(self, source_wallet: str) -> dict:
        """Compact per-agent summary for receipt attestation / dashboards."""
        agent = (source_wallet or "").lower()
        with self._lock:
            hist = list(self._hist.get(agent, []))
            payees = len(self._payees.get(agent, set()))
        amounts = [o.amount for o in hist]
        return {
            "observations": len(hist),
            "distinct_payees": payees,
            "median_amount": round(statistics.median(amounts), 4) if amounts else None,
        }

    # ── Persistence ─────────────────────────────────────────────────
    def to_state(self) -> dict:
        with self._lock:
            return {
                "version": "behavioral-history-v1",
                "agents": {
                    agent: [o.to_dict() for o in obs]
                    for agent, obs in self._hist.items()
                },
            }

    def load_state(self, state: dict) -> None:
        agents = (state or {}).get("agents", {})
        with self._lock:
            self._hist = {}
            self._payees = {}
            for agent, obs_list in agents.items():
                a = agent.lower()
                obs = [Observation.from_dict(d) for d in obs_list][-self._max:]
                self._hist[a] = obs
                self._payees[a] = {o.payee for o in obs}

    def persist(self, path: str = HISTORY_STATE_PATH) -> None:
        try:
            from app import storage
            storage.store_json(path, self.to_state())
        except Exception as e:  # noqa: BLE001
            logger.debug("Behavioral persist skipped: %s", e)

    def restore(self, path: str = HISTORY_STATE_PATH) -> bool:
        try:
            from app import storage
            state = storage.load_json(path)
            if state:
                self.load_state(state)
                logger.info("Restored behavioral history for %d agent(s)",
                            len(state.get("agents", {})))
                return True
        except Exception as e:  # noqa: BLE001
            logger.debug("Behavioral restore skipped: %s", e)
        return False


# Module singleton, lazily restored from persistence on first access.
_engine: BehavioralEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> BehavioralEngine:
    """Return the process-wide behavioral engine, restoring history once."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                eng = BehavioralEngine()
                eng.restore()
                _engine = eng
    return _engine
