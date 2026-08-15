"""Agent framework integrations for Verigate.

Drop-in tools for LangChain, CrewAI, and OpenAI function calling.
Each tool wraps Verigate's screening API so any agent framework
can check payments before executing them.

Usage with LangChain:
    from verigate.integrations import VerigateToolkit
    toolkit = VerigateToolkit(base_url="https://verigate.cloud")
    agent = initialize_agent(tools=toolkit.get_tools(), llm=llm)

Usage with CrewAI:
    from verigate.integrations import VerigateCrewTool
    screen_tool = VerigateCrewTool(base_url="https://verigate.cloud")
    agent = Agent(role="Purchasing Agent", tools=[screen_tool])

Usage with OpenAI function calling:
    from verigate.integrations import verigate_openai_schema
    tools = [verigate_openai_schema()]
"""

from __future__ import annotations

import json
import os
from typing import Any

VERIGATE_URL = os.environ.get("VERIGATE_URL", "https://verigate.cloud")


def _check_payment(payee: str, amount: float, service: str = "", reason: str = "") -> dict:
    """Call Verigate's screening API. Works offline or against live endpoint."""
    try:
        import httpx
        resp = httpx.post(
            f"{VERIGATE_URL}/api/check",
            json={"payee": payee, "amount": str(amount), "service": service, "reason": reason},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    # Offline fallback: use local scorer
    try:
        from circle.risk_scorer import evaluate_risk
        result = evaluate_risk(
            payee=payee, amount=str(amount), service=service, reason=reason,
            source_wallet="0x0000000000000000000000000000000000000000", chain="BASE",
        )
        return {
            "decision": result.decision,
            "score": result.score,
            "band": result.band,
            "signals": result.signals,
            "rationale": result.rationale,
        }
    except Exception as e:
        return {"decision": "DENY", "score": 100, "rationale": f"Screening unavailable: {e}"}


def _format_result(result: dict) -> str:
    """Format screening result for agent consumption."""
    decision = result.get("decision", "DENY")
    score = result.get("score", 100)
    rationale = result.get("rationale", "")
    signals = result.get("signals", [])
    governance = result.get("governance", {})

    parts = [f"Decision: {decision} (score {score}/100)"]
    if rationale:
        parts.append(f"Rationale: {rationale}")
    if signals:
        parts.append(f"Signals: {', '.join(signals)}")
    if governance:
        inc = governance.get("incident", {})
        if inc.get("severity"):
            parts.append(f"Incident: {inc['severity']} — {inc.get('summary', '')}")
        recs = governance.get("policy_recommendations", [])
        if recs:
            parts.append(f"Recommendations: {', '.join(r.get('change', '') for r in recs)}")

    return "\n".join(parts)


# ── LangChain Integration ───────────────────────────────────────────

def _make_langchain_tool(base_url: str = VERIGATE_URL):
    """Create a LangChain tool for payment screening."""
    try:
        from langchain_core.tools import tool

        @tool
        def check_payment_safety(payee: str, amount: float, service: str = "", reason: str = "") -> str:
            """Check if a payment is safe before executing it through Verigate.

            Screens the payment against OFAC sanctions, injection detection,
            behavioral anomaly signals, and policy rules. Returns APPROVE,
            STEP_UP, or DENY with explanation.

            Args:
                payee: The recipient wallet address (e.g. 0x742d...)
                amount: Payment amount in USDC
                service: Service being paid for (e.g. "market-data-api")
                reason: Why this payment is being made
            """
            result = _check_payment(payee, amount, service, reason)
            return _format_result(result)

        return check_payment_safety
    except ImportError:
        return None


class VerigateToolkit:
    """LangChain-compatible toolkit wrapping Verigate's screening API.

    Usage:
        from verigate.integrations import VerigateToolkit
        toolkit = VerigateToolkit(base_url="https://verigate.cloud")
        agent = initialize_agent(tools=toolkit.get_tools(), llm=llm)
    """

    def __init__(self, base_url: str = VERIGATE_URL):
        self.base_url = base_url

    def get_tools(self) -> list:
        """Return LangChain tools for Verigate screening."""
        tool = _make_langchain_tool(self.base_url)
        if tool is not None:
            return [tool]
        # Fallback: return a plain function wrapper if langchain not installed
        return [self._plain_tool()]

    def _plain_tool(self):
        """Plain function fallback when LangChain is not installed."""
        def check_payment_safety(payee: str, amount: float, service: str = "", reason: str = "") -> str:
            result = _check_payment(payee, amount, service, reason)
            return _format_result(result)
        check_payment_safety.__name__ = "check_payment_safety"
        check_payment_safety.__doc__ = "Screen a USDC payment through Verigate. Returns APPROVE/STEP_UP/DENY."
        return check_payment_safety


# ── CrewAI Integration ──────────────────────────────────────────────

def _make_crewai_tool(base_url: str = VERIGATE_URL):
    """Create a CrewAI tool for payment screening."""
    try:
        from crewai.tools import tool

        @tool("verify_payment")
        def verify_payment(payee: str, amount: float, service: str = "", reason: str = "") -> str:
            """Verify a payment is safe before executing. Screens against sanctions,
            injection patterns, and behavioral anomalies via Verigate.

            Args:
                payee: Recipient wallet address
                amount: Payment amount in USDC
                service: Service description
                reason: Payment reason
            """
            result = _check_payment(payee, amount, service, reason)
            return _format_result(result)

        return verify_payment
    except ImportError:
        return None


class VerigateCrewTool:
    """CrewAI-compatible tool wrapping Verigate's screening API.

    Usage:
        from verigate.integrations import VerigateCrewTool
        screen_tool = VerigateCrewTool(base_url="https://verigate.cloud")
        agent = Agent(role="Purchasing Agent", tools=[screen_tool])
    """

    def __init__(self, base_url: str = VERIGATE_URL):
        self.base_url = base_url
        self.name = "verify_payment"
        self.description = (
            "Screen a USDC payment through Verigate before executing. "
            "Returns APPROVE, STEP_UP, or DENY with risk score and explanation."
        )
        self._inner = _make_crewai_tool(base_url)

    def run(self, payee: str, amount: float, service: str = "", reason: str = "") -> str:
        if self._inner is not None:
            return self._inner(payee=payee, amount=amount, service=service, reason=reason)
        result = _check_payment(payee, amount, service, reason)
        return _format_result(result)

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        return self.run(*args, **kwargs)


# ── OpenAI Function Calling Schema ──────────────────────────────────

openai_tool_schema = {
    "type": "function",
    "function": {
        "name": "check_payment_safety",
        "description": "Screen a USDC payment through Verigate before executing. "
                       "Returns APPROVE, STEP_UP, or DENY with risk score and explanation.",
        "parameters": {
            "type": "object",
            "properties": {
                "payee": {"type": "string", "description": "Recipient wallet address (0x...)"},
                "amount": {"type": "number", "description": "Payment amount in USDC"},
                "service": {"type": "string", "description": "Service being paid for"},
                "reason": {"type": "string", "description": "Why this payment is being made"},
            },
            "required": ["payee", "amount"],
        },
    },
}


def verigate_openai_schema() -> dict:
    """Return the OpenAI function calling schema for Verigate.

    Usage:
        from verigate.integrations import verigate_openai_schema
        response = openai.chat.completions.create(
            model="gpt-4",
            tools=[verigate_openai_schema()],
            messages=messages
        )
    """
    return openai_tool_schema


def handle_tool_call(function_name: str, arguments: dict) -> str:
    """Handle an OpenAI function call for payment screening."""
    if function_name == "check_payment_safety":
        result = _check_payment(
            payee=arguments["payee"],
            amount=float(arguments["amount"]),
            service=arguments.get("service", ""),
            reason=arguments.get("reason", ""),
        )
        return json.dumps(result)
    return json.dumps({"error": f"Unknown function: {function_name}"})


# ── Lazy-loaded tools ───────────────────────────────────────────────
# Only instantiate if the framework is installed

langchain_check_payment = _make_langchain_tool()
crewai_check_payment = _make_crewai_tool()
