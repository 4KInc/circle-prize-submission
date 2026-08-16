"""RAG knowledge base for the evidence validator.

Stores screening history as embeddings and retrieves relevant past events
to give Gemini context across decisions. Without this, Gemini evaluates
every STEP_UP case in isolation. With it, Gemini can see:

- This agent's past STEP_UP outcomes (learned trust)
- Similar cases across the platform (normative context)
- Carrier feedback on past denials (ground truth)
- Known attack patterns that matched (threat intelligence)

Storage: in-memory with JSON persistence to GCS (survives Cloud Run restarts).
Embeddings: Gemini text-embedding-004 model.
Retrieval: cosine similarity, top-K nearest neighbors.

No external vector DB dependency. The knowledge base is small enough
(~1KB per record, 10K records = 10MB) that in-memory search is fast.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("circle.rag_store")

RAG_STATE_PATH = "rag/screening_history.json"


@dataclass
class ScreeningRecord:
    """A historical screening event stored in the RAG knowledge base."""

    record_id: str
    agent_id: str
    payee: str
    amount: float
    service: str
    score: int
    decision: str  # APPROVE / STEP_UP / DENY
    step_up_outcome: str = ""  # CONFIRM / DENY (if STEP_UP)
    signals: list[str] = field(default_factory=list)
    rationale: str = ""
    carrier_feedback: str = ""
    timestamp: str = ""
    embedding: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("embedding", None)  # Don't serialize embeddings to JSON display
        return d

    def context_text(self) -> str:
        """Human-readable summary for Gemini context."""
        parts = [
            f"${self.amount:.2f} to {self.payee[:12]}... for '{self.service}'",
            f"Score {self.score}, Decision: {self.decision}",
        ]
        if self.step_up_outcome:
            parts.append(f"STEP_UP outcome: {self.step_up_outcome}")
        if self.carrier_feedback:
            parts.append(f"Carrier feedback: {self.carrier_feedback}")
        if self.signals:
            parts.append(f"Signals: {', '.join(self.signals[:3])}")
        return " | ".join(parts)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_text(text: str) -> list[float]:
    """Create embedding using Gemini text-embedding-004."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("No Gemini API key for embedding, returning empty")
        return []

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
        )
        return list(response.embeddings[0].values)
    except Exception as e:
        logger.warning("Embedding failed: %s", e)
        return []


def _build_query_text(context: dict) -> str:
    """Build a text query from a payment context for embedding."""
    parts = [
        f"agent:{context.get('agent_id', 'unknown')}",
        f"payee:{context.get('payee', '')[:16]}",
        f"amount:{context.get('amount', 0)}",
        f"service:{context.get('service', '')}",
    ]
    signals = context.get("scorer_signals", [])
    if signals:
        parts.append(f"signals:{','.join(signals[:5])}")
    reason = context.get("reason", "")
    if reason:
        parts.append(f"reason:{reason[:100]}")
    return " ".join(parts)


class RAGStore:
    """In-memory vector store with cosine similarity retrieval.

    Thread-safe. Persists to GCS via app.storage on every write.
    """

    def __init__(self) -> None:
        self._records: list[ScreeningRecord] = []
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return len(self._records)

    def add(self, record: ScreeningRecord) -> None:
        """Add a screening record to the knowledge base."""
        if not record.embedding:
            text = _build_query_text({
                "agent_id": record.agent_id,
                "payee": record.payee,
                "amount": record.amount,
                "service": record.service,
                "scorer_signals": record.signals,
            })
            record.embedding = _embed_text(text)

        with self._lock:
            self._records.append(record)

        logger.info(
            "RAG store: added record %s (size=%d, has_embedding=%s)",
            record.record_id, self.size, bool(record.embedding),
        )
        self._persist()

    def add_carrier_feedback(self, record_id: str, feedback: str) -> None:
        """Update a record with carrier feedback (ground truth)."""
        with self._lock:
            for r in self._records:
                if r.record_id == record_id:
                    r.carrier_feedback = feedback
                    logger.info("RAG store: carrier feedback added to %s", record_id)
                    break
        self._persist()

    def search(
        self,
        context: dict,
        top_k: int = 5,
        agent_only: bool = False,
    ) -> list[ScreeningRecord]:
        """Retrieve the most relevant historical records for a payment context.

        Args:
            context: Current payment context dict.
            top_k: Number of records to retrieve.
            agent_only: If True, only retrieve records from the same agent.

        Returns:
            List of ScreeningRecord sorted by relevance (most similar first).
        """
        query_text = _build_query_text(context)
        query_embedding = _embed_text(query_text)

        if not query_embedding:
            # No embedding available, fall back to recency-based retrieval
            return self._fallback_search(context, top_k, agent_only)

        agent_id = context.get("agent_id", "")

        with self._lock:
            scored = []
            for record in self._records:
                if agent_only and record.agent_id != agent_id:
                    continue
                if not record.embedding:
                    continue
                sim = _cosine_similarity(query_embedding, record.embedding)
                scored.append((sim, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    def search_by_agent(self, agent_id: str, top_k: int = 5) -> list[ScreeningRecord]:
        """Retrieve the most recent records for a specific agent."""
        with self._lock:
            agent_records = [r for r in self._records if r.agent_id == agent_id]
        agent_records.sort(key=lambda r: r.timestamp, reverse=True)
        return agent_records[:top_k]

    def search_cross_agent(
        self,
        context: dict,
        exclude_agent: str = "",
        top_k: int = 5,
    ) -> list[ScreeningRecord]:
        """Retrieve similar cases from OTHER agents (anonymized)."""
        query_text = _build_query_text(context)
        query_embedding = _embed_text(query_text)

        if not query_embedding:
            return []

        with self._lock:
            scored = []
            for record in self._records:
                if record.agent_id == exclude_agent:
                    continue
                if not record.embedding:
                    continue
                sim = _cosine_similarity(query_embedding, record.embedding)
                scored.append((sim, record))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Anonymize: redact agent_id and payee for cross-agent results
        results = []
        for _, r in scored[:top_k]:
            anonymized = ScreeningRecord(
                record_id=r.record_id,
                agent_id="[other-agent]",
                payee=r.payee[:6] + "...",
                amount=r.amount,
                service=r.service,
                score=r.score,
                decision=r.decision,
                step_up_outcome=r.step_up_outcome,
                signals=r.signals,
                rationale="",
                carrier_feedback=r.carrier_feedback,
                timestamp=r.timestamp,
            )
            results.append(anonymized)
        return results

    def _fallback_search(
        self, context: dict, top_k: int, agent_only: bool
    ) -> list[ScreeningRecord]:
        """Fallback when embeddings aren't available: recency + same agent."""
        agent_id = context.get("agent_id", "")
        with self._lock:
            if agent_only:
                candidates = [r for r in self._records if r.agent_id == agent_id]
            else:
                candidates = list(self._records)
        candidates.sort(key=lambda r: r.timestamp, reverse=True)
        return candidates[:top_k]

    def format_for_gemini(
        self,
        agent_records: list[ScreeningRecord],
        cross_records: list[ScreeningRecord],
    ) -> str:
        """Format retrieved records into context text for Gemini prompt."""
        lines = []

        if agent_records:
            lines.append("THIS AGENT'S HISTORY:")
            for r in agent_records:
                lines.append(f"  - {r.context_text()}")
            outcomes = [r.step_up_outcome for r in agent_records if r.step_up_outcome]
            if outcomes:
                confirms = outcomes.count("CONFIRM")
                denies = outcomes.count("DENY")
                lines.append(
                    f"  Summary: {confirms} STEP_UP resolved to CONFIRM, "
                    f"{denies} resolved to DENY out of {len(outcomes)} total."
                )

        if cross_records:
            lines.append("\nSIMILAR CASES ACROSS PLATFORM (anonymized):")
            for r in cross_records:
                lines.append(f"  - {r.context_text()}")

        carrier_feedback = [
            r for r in (agent_records + cross_records) if r.carrier_feedback
        ]
        if carrier_feedback:
            lines.append("\nCARRIER FEEDBACK ON SIMILAR CASES:")
            for r in carrier_feedback:
                lines.append(f"  - {r.carrier_feedback}")

        return "\n".join(lines) if lines else "No relevant history found."

    def stats(self) -> dict:
        """Return RAG store statistics."""
        with self._lock:
            total = len(self._records)
            with_embedding = sum(1 for r in self._records if r.embedding)
            with_feedback = sum(1 for r in self._records if r.carrier_feedback)
            agents = len(set(r.agent_id for r in self._records))
            decisions = {}
            for r in self._records:
                decisions[r.decision] = decisions.get(r.decision, 0) + 1
        return {
            "total_records": total,
            "with_embeddings": with_embedding,
            "with_carrier_feedback": with_feedback,
            "unique_agents": agents,
            "decisions": decisions,
        }

    # -- Persistence --

    def to_json(self) -> list[dict]:
        """Serialize for GCS persistence."""
        with self._lock:
            return [
                {**asdict(r)}
                for r in self._records
            ]

    def restore(self, data: list[dict]) -> int:
        """Restore from GCS persistence."""
        count = 0
        for d in data:
            try:
                record = ScreeningRecord(
                    record_id=d["record_id"],
                    agent_id=d["agent_id"],
                    payee=d["payee"],
                    amount=float(d["amount"]),
                    service=d["service"],
                    score=int(d["score"]),
                    decision=d["decision"],
                    step_up_outcome=d.get("step_up_outcome", ""),
                    signals=d.get("signals", []),
                    rationale=d.get("rationale", ""),
                    carrier_feedback=d.get("carrier_feedback", ""),
                    timestamp=d.get("timestamp", ""),
                    embedding=d.get("embedding", []),
                )
                with self._lock:
                    self._records.append(record)
                count += 1
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed RAG record: %s", e)
        logger.info("RAG store: restored %d records", count)
        return count

    def _persist(self) -> None:
        """Persist to GCS (best-effort)."""
        try:
            from app.storage import save_json
            save_json(RAG_STATE_PATH, self.to_json())
        except Exception:
            pass  # GCS unavailable locally


# -- Singleton --

_store: RAGStore | None = None
_store_lock = threading.Lock()


def get_rag_store() -> RAGStore:
    """Get or create the singleton RAG store."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = RAGStore()
                # Try to restore from GCS
                try:
                    from app.storage import load_json
                    data = load_json(RAG_STATE_PATH)
                    if data:
                        _store.restore(data)
                except Exception:
                    pass
    return _store
