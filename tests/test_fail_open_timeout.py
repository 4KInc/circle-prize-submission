"""Screening must fail open in VERDICT and in LATENCY.

The client already approved when Verigate was unreachable, but the request
timeout was 10 seconds, so an unresponsive Verigate stalled the caller for ten
seconds before approving. For a sub-second payment router that is an outage
with a friendly decision attached -- the route was blocked either way.

The budget is now 1.0s, roughly seven times the measured warm p95 (142ms), so
it does not fire against a healthy service and caps the worst case at a
second. These tests pin both halves: the verdict and the wall-clock.
"""

from __future__ import annotations

import http.server
import threading
import time

import pytest

import integrations.x402_screening as screening


@pytest.fixture
def hanging_server(monkeypatch):
    """A server that accepts the request and never answers."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            time.sleep(30)
        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(screening, "VERIGATE_URL", f"http://127.0.0.1:{srv.server_address[1]}")
    yield
    srv.shutdown()


def _screen(**kw):
    return screening.screen_payment(
        payee="blockrun.ai/openai/gpt-5.6-luna", amount=0.005,
        service="llm-inference", reason="agent LLM call", **kw)


class TestLatencyBudget:
    def test_default_budget_is_sub_second(self):
        assert screening.DEFAULT_TIMEOUT_SECONDS <= 1.0

    def test_a_hung_verigate_does_not_stall_the_caller(self, hanging_server):
        """THE BUG: this used to take ten seconds."""
        start = time.time()
        result = _screen()
        elapsed = time.time() - start
        assert result.decision == "APPROVE"
        assert elapsed < 3.0, f"caller stalled {elapsed:.1f}s"

    def test_caller_can_tighten_the_budget(self, hanging_server):
        start = time.time()
        _screen(timeout=0.25)
        assert time.time() - start < 2.0


class TestVerdictUnchanged:
    def test_timeout_fails_open_by_default(self, hanging_server):
        r = _screen()
        assert r.decision == "APPROVE"
        assert r.blocked is False
        assert "verigate_unavailable" in r.signals

    def test_timeout_denies_when_fail_closed(self, hanging_server):
        r = _screen(fail_closed=True)
        assert r.decision == "DENY"
        assert r.blocked is True
        assert "verigate_unavailable" in r.signals

    def test_unreachable_still_fails_open(self, monkeypatch):
        monkeypatch.setattr(screening, "VERIGATE_URL", "http://127.0.0.1:9")
        assert _screen().decision == "APPROVE"
