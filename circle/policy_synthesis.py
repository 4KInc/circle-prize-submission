"""Gemini-powered policy synthesis for Circle Agent Wallets.

An agent describes what it wants to do in natural language:
  "I need to buy market data from Bloomberg and Reuters, max $5/day per vendor"

Gemini translates this to a structured spending policy that can be enforced
deterministically by Circle's wallet infrastructure.

Trust model:
  - Gemini SYNTHESIZES the policy (translates intent to structure)
  - Hard gates in Python CONSTRAIN the output (caps, minimums, blocked patterns)
  - The policy engine ENFORCES the result deterministically (no LLM at enforcement time)
  - If confidence < 0.7, the policy requires human review before activation

This means Gemini is in the CONFIGURATION path, not the AUTHORIZATION path.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger("circle.policy_synthesis")


@dataclass
class SynthesizedPolicy:
    """Output of Gemini policy synthesis. Validated before enforcement."""
    allowed_payees: list[str] = field(default_factory=list)
    allowed_service_categories: list[str] = field(default_factory=list)
    max_amount_per_tx: float = 1.0
    max_amount_per_day: float = 10.0
    rate_limit_per_hour: int = 10
    blocked_patterns: list[str] = field(default_factory=lambda: ["OVERRIDE", "IGNORE", "BYPASS"])
    confidence: float = 0.0
    reasoning: str = ""
    requires_human_review: bool = True
    gemini_available: bool = True

    def to_dict(self) -> dict:
        return {
            "allowed_payees": self.allowed_payees,
            "allowed_service_categories": self.allowed_service_categories,
            "max_amount_per_tx": self.max_amount_per_tx,
            "max_amount_per_day": self.max_amount_per_day,
            "rate_limit_per_hour": self.rate_limit_per_hour,
            "blocked_patterns": self.blocked_patterns,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "requires_human_review": self.requires_human_review,
            "gemini_available": self.gemini_available,
        }

    def to_circle_policy(self) -> dict:
        """Convert to Circle-compatible wallet spending policy format."""
        return {
            "name": "gemini-synthesized-policy",
            "rules": [
                {
                    "type": "transfer_limit",
                    "max_amount": str(self.max_amount_per_tx),
                    "max_amount_per_day": str(self.max_amount_per_day),
                    "asset": "USDC",
                },
                {
                    "type": "rate_limit",
                    "max_transfers_per_hour": self.rate_limit_per_hour,
                },
            ],
            "metadata": {
                "synthesized_by": "gemini-2.5-flash",
                "confidence": self.confidence,
                "requires_human_review": self.requires_human_review,
                "allowed_services": self.allowed_service_categories,
                "blocked_patterns": self.blocked_patterns,
            },
        }


# Gemini structured output schema
_POLICY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "allowed_payees": {"type": "ARRAY", "items": {"type": "STRING"}},
        "allowed_service_categories": {"type": "ARRAY", "items": {"type": "STRING"}},
        "max_amount_per_tx": {"type": "NUMBER"},
        "max_amount_per_day": {"type": "NUMBER"},
        "rate_limit_per_hour": {"type": "INTEGER"},
        "blocked_patterns": {"type": "ARRAY", "items": {"type": "STRING"}},
        "confidence": {"type": "NUMBER"},
        "reasoning": {"type": "STRING"},
    },
    "required": [
        "allowed_service_categories", "max_amount_per_tx", "max_amount_per_day",
        "rate_limit_per_hour", "blocked_patterns", "confidence", "reasoning",
    ],
}


def _conservative_default(description: str) -> SynthesizedPolicy:
    """Fallback when Gemini is unavailable — conservative defaults."""
    return SynthesizedPolicy(
        max_amount_per_tx=1.0,
        max_amount_per_day=10.0,
        rate_limit_per_hour=5,
        confidence=0.0,
        reasoning=f"Gemini unavailable. Conservative defaults applied for: {description[:100]}",
        requires_human_review=True,
        gemini_available=False,
    )


# Hard safety constraints — Python enforces these regardless of Gemini output
MAX_AMOUNT_PER_TX_CEILING = 100.0
MAX_AMOUNT_PER_DAY_CEILING = 500.0
MIN_BLOCKED_PATTERNS = 1
HUMAN_REVIEW_CONFIDENCE_THRESHOLD = 0.7


def synthesize_policy(
    agent_description: str,
    existing_policy: dict | None = None,
) -> SynthesizedPolicy:
    """Translate natural language agent intent to a structured spending policy.

    Gemini synthesizes. Python constrains. The policy engine enforces deterministically.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return _conservative_default(agent_description)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        existing_json = json.dumps(existing_policy or {}, indent=2)

        prompt = f"""An AI agent wants to configure its Circle wallet spending policy.

AGENT'S DESCRIPTION OF WHAT IT NEEDS:
"{agent_description}"

CURRENT POLICY (if any):
{existing_json}

Synthesize a Circle-compatible spending policy. Rules:
1. Never set max_amount_per_tx > {MAX_AMOUNT_PER_TX_CEILING}
2. Never set max_amount_per_day > {MAX_AMOUNT_PER_DAY_CEILING}
3. If the description mentions "unlimited" or "no limit", set conservative caps and explain why
4. Always include at least {MIN_BLOCKED_PATTERNS} blocked_pattern for injection attempts (e.g. "OVERRIDE", "IGNORE", "BYPASS")
5. Set confidence between 0.0-1.0 based on how clear and specific the description is
6. If the description is vague, set lower confidence and tighter limits
7. allowed_payees should only be set if the agent explicitly names specific addresses
8. Be specific in reasoning about WHY you chose each limit

Provide the structured policy."""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_POLICY_SCHEMA,
            ),
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text)

        policy = SynthesizedPolicy(
            allowed_payees=data.get("allowed_payees", []),
            allowed_service_categories=data.get("allowed_service_categories", []),
            max_amount_per_tx=min(float(data.get("max_amount_per_tx", 1.0)), MAX_AMOUNT_PER_TX_CEILING),
            max_amount_per_day=min(float(data.get("max_amount_per_day", 10.0)), MAX_AMOUNT_PER_DAY_CEILING),
            rate_limit_per_hour=max(1, min(int(data.get("rate_limit_per_hour", 10)), 100)),
            blocked_patterns=data.get("blocked_patterns", ["OVERRIDE", "IGNORE", "BYPASS"]),
            confidence=min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
            reasoning=data.get("reasoning", ""),
            gemini_available=True,
        )

        # Hard gates — enforced in Python, not by Gemini
        if policy.max_amount_per_tx > MAX_AMOUNT_PER_TX_CEILING:
            policy.max_amount_per_tx = MAX_AMOUNT_PER_TX_CEILING
        if policy.max_amount_per_day > MAX_AMOUNT_PER_DAY_CEILING:
            policy.max_amount_per_day = MAX_AMOUNT_PER_DAY_CEILING
        if len(policy.blocked_patterns) < MIN_BLOCKED_PATTERNS:
            policy.blocked_patterns = ["OVERRIDE", "IGNORE", "BYPASS"]
        if policy.confidence < HUMAN_REVIEW_CONFIDENCE_THRESHOLD:
            policy.requires_human_review = True
        else:
            policy.requires_human_review = False

        logger.info(
            "Policy synthesized: max_tx=$%.2f, max_day=$%.2f, confidence=%.2f, review=%s",
            policy.max_amount_per_tx, policy.max_amount_per_day,
            policy.confidence, policy.requires_human_review,
        )
        return policy

    except Exception as e:
        logger.warning("Policy synthesis failed: %s", e)
        return _conservative_default(agent_description)
