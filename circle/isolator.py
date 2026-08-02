"""Forensic Recorder — incident documentation and analysis.

Circle's Action Gate blocks unauthorized payments. Circle's Execution
Harness isolates agents in microVMs. We don't duplicate any of that.

What Circle DOESN'T do is produce signed, independently verifiable
forensic evidence of what happened. That's what the Forensic Recorder does:

1. Classifies incident severity from denial patterns
2. Produces a signed forensic record (Ed25519, independently verifiable)
3. Publishes reputation events to ERC-8004 on-chain registry
4. Runs cross-agent correlation to detect systemic attacks
5. Generates actionable recommendations for Circle's Action Gate

Circle enforces. Verigate proves.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "engine")
if os.path.isdir(ENGINE_PATH) and ENGINE_PATH not in sys.path:
    sys.path.insert(0, ENGINE_PATH)

from gateway.canonical import canonicalize
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

logger = logging.getLogger("circle.isolator")


@dataclass
class ForensicRecord:
    """Signed forensic record documenting an incident.

    This is NOT an enforcement action — Circle handles enforcement.
    This is cryptographic evidence that proves what happened, when,
    why, and what should be done about it.
    """
    record_id: str
    tenant: str
    agent_id: str
    severity: str
    trigger: dict
    findings: list[dict]
    recommendations: list[dict]
    recorded_at: str
    receipt_hash: str = ""
    signature: str = ""
    kid: str = ""

    def body_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "tenant": self.tenant,
            "agent_id": self.agent_id,
            "severity": self.severity,
            "trigger": self.trigger,
            "findings": self.findings,
            "recommendations": self.recommendations,
            "recorded_at": self.recorded_at,
            "schema_version": "forensic-record-v0.2",
        }

    def envelope_dict(self) -> dict:
        return {
            "body": self.body_dict(),
            "sig": {
                "alg": "EdDSA",
                "kid": self.kid,
                "value": self.signature,
            },
            "receipt_hash": self.receipt_hash,
        }


# Keep backward compat alias
IsolationRecord = ForensicRecord


def classify_severity(denial_reasons: list[str]) -> str:
    """Classify the severity of a denied payment.

    Returns HIGH or CRITICAL based on the denial reasons.
    Prompt injection indicators -> CRITICAL.
    Multiple policy violations -> HIGH.
    Single violation -> MEDIUM (no forensic record triggered).
    """
    reasons_lower = " ".join(denial_reasons).lower()

    injection_keywords = [
        "injection", "attacker", "exploit", "malicious",
        "ignore previous", "override", "bypass",
    ]
    if any(kw in reasons_lower for kw in injection_keywords):
        return "CRITICAL"

    if len(denial_reasons) >= 2:
        return "HIGH"

    for reason in denial_reasons:
        if "AMOUNT_EXCEEDS_CAP" in reason:
            try:
                parts = reason.split(":")[-1].split(">")
                attempted = float(parts[0])
                cap = float(parts[1])
                if attempted > cap * 10:
                    return "HIGH"
            except (ValueError, IndexError):
                pass

    return "MEDIUM"


def _analyze_attack_vector(denial_reasons: list[str], intent_context: dict | None) -> list[dict]:
    """Analyze what happened using Gemini for deep forensic analysis.

    Falls back to deterministic analysis if Gemini is unavailable.
    This is Gemini doing what it's good at (reasoning about context)
    while the receipt chain does what code is good at (cryptographic proof).
    """
    # Try Gemini-powered forensic analysis first
    gemini_findings = _gemini_forensic_analysis(denial_reasons, intent_context)
    if gemini_findings:
        return gemini_findings

    # Deterministic fallback
    return _deterministic_analysis(denial_reasons, intent_context)


def _gemini_forensic_analysis(denial_reasons: list[str], intent_context: dict | None) -> list[dict] | None:
    """Use Gemini to perform deep forensic analysis of the incident."""
    try:
        from google import genai
    except ImportError:
        return None

    import json
    import os
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    client = genai.Client(api_key=api_key)
    prompt = f"""You are a forensic analyst for an AI agent payment system.

An AI agent attempted a payment that was denied. Analyze the incident and produce forensic findings.

DENIAL REASONS: {json.dumps(denial_reasons)}
INTENT CONTEXT: {json.dumps(intent_context or {})}

For each finding, determine:
1. The attack vector or violation type
2. What evidence supports this classification
3. What Circle's Action Gate and wallet policies should do in response

Respond with a JSON array of findings:
[{{
  "finding": "SHORT_CODE (e.g. PROMPT_INJECTION_DETECTED, UNAUTHORIZED_PAYEE, AMOUNT_VIOLATION)",
  "evidence": "Specific evidence from the denial reasons and context",
  "detail": "Detailed analysis: what happened, how the agent's context was likely compromised, and what Circle's enforcement layer should review"
}}]

Be specific. Reference the actual denial reasons and payee addresses. Respond ONLY with the JSON array."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        findings = json.loads(text)
        if isinstance(findings, list) and findings:
            logger.info(f"Gemini forensic analysis: {len(findings)} findings")
            return findings
    except Exception as e:
        logger.warning(f"Gemini forensic analysis failed: {e}")

    return None


def _deterministic_analysis(denial_reasons: list[str], intent_context: dict | None) -> list[dict]:
    """Deterministic fallback forensic analysis."""
    findings = []
    reasons_lower = " ".join(denial_reasons).lower()

    if any(kw in reasons_lower for kw in ["override", "ignore", "bypass", "injection"]):
        findings.append({
            "finding": "PROMPT_INJECTION_DETECTED",
            "evidence": "Denial reasons contain adversarial instruction patterns",
            "detail": "The agent's context appears to have been poisoned with instructions "
                      "to override policy controls. Circle's Input Guardrails should be "
                      "reviewed for this attack vector.",
        })

    if any("RESOURCE_OUT_OF_SCOPE" in r or "NOT_IN_ALLOWLIST" in r for r in denial_reasons):
        payee = intent_context.get("payee", "unknown") if intent_context else "unknown"
        findings.append({
            "finding": "UNAUTHORIZED_PAYEE",
            "evidence": f"Payment attempted to off-allowlist address: {payee}",
            "detail": "Circle's Action Gate independently blocked this at the wallet layer. "
                      "This receipt proves the attempt was also caught at the Verigate layer.",
        })

    if any("AMOUNT_EXCEEDS_CAP" in r for r in denial_reasons):
        amount = intent_context.get("amount", "unknown") if intent_context else "unknown"
        findings.append({
            "finding": "AMOUNT_VIOLATION",
            "evidence": f"Payment of {amount} USDC exceeds configured cap",
            "detail": "Circle's wallet spending policies independently enforce amount limits. "
                      "This receipt documents the exact amount attempted and the cap in effect.",
        })

    if not findings:
        findings.append({
            "finding": "POLICY_VIOLATION",
            "evidence": f"Denial reasons: {', '.join(denial_reasons)}",
            "detail": "Payment violated one or more policy rules.",
        })

    return findings


def _generate_recommendations(severity: str, denial_reasons: list[str], agent_id: str) -> list[dict]:
    """Generate actionable recommendations for Circle's enforcement layer.

    These target specific Circle components with concrete actions.
    """
    recs = []

    if severity == "CRITICAL":
        recs.append({
            "target": "CIRCLE_ACTION_GATE",
            "action": "UPDATE_INPUT_GUARDRAILS",
            "detail": f"Agent {agent_id} received adversarial instructions. "
                      "Review and tighten Circle's pre-LLM Input Guardrails to filter "
                      "this attack pattern.",
            "cli_hint": "Configure via Circle Developer Console > Agent Settings > Input Guardrails",
        })
        recs.append({
            "target": "CIRCLE_WALLET_POLICY",
            "action": "REDUCE_SPENDING_LIMIT",
            "detail": f"Recommend reducing daily spending limit for agent {agent_id}'s "
                      "wallet via Circle Developer Console until the attack vector is patched.",
            "cli_hint": "circle wallet limit set --daily 0 --per-tx 0",
        })

    if any("RESOURCE_OUT_OF_SCOPE" in r for r in denial_reasons):
        recs.append({
            "target": "CIRCLE_WALLET_POLICY",
            "action": "TIGHTEN_ALLOWLIST",
            "detail": "The agent attempted payment to an off-allowlist address. "
                      "Verify Circle's wallet allowlist is current and consider "
                      "enabling strict mode.",
            "cli_hint": "circle wallet allowlist add/remove --address <addr>",
        })

    if severity in ("HIGH", "CRITICAL"):
        recs.append({
            "target": "OPERATOR",
            "action": "REVIEW_AGENT_CONTEXT",
            "detail": f"Investigate how agent {agent_id}'s context was compromised. "
                      "Check data sources, tool outputs, and prompt pipelines for "
                      "injection vectors.",
        })

    return recs


class Isolator:
    """Forensic recorder for agent payment incidents.

    Does NOT enforce — Circle's Action Gate and MPC co-signer handle
    enforcement. Instead, produces signed forensic evidence that:

    1. Proves what happened (findings with evidence)
    2. Recommends what to do (actionable items for Circle's stack)
    3. Publishes reputation (ERC-8004 on-chain registry)
    4. Detects systemic attacks (cross-agent correlation)
    """

    def __init__(
        self,
        tenant: str,
        private_key: Ed25519PrivateKey,
        kid: str,
        wallet_address: str | None = None,
        chain: str = "BASE-SEPOLIA",
        reputation_writer=None,
        correlation_engine=None,
    ):
        self.tenant = tenant
        self._private_key = private_key
        self._kid = kid
        self._wallet_address = wallet_address
        self._chain = chain
        self.records: list[ForensicRecord] = []
        self._reputation_writer = reputation_writer
        self._correlation_engine = correlation_engine

    def evaluate_and_contain(
        self,
        agent_id: str,
        denial_reasons: list[str],
        denial_receipt_hash: str,
        intent_context: dict | None = None,
    ) -> ForensicRecord | None:
        """Analyze a denial and produce forensic evidence if HIGH/CRITICAL.

        Does NOT enforce (Circle handles that). Produces:
        - Signed forensic record with findings and evidence
        - Recommendations for Circle's Action Gate / wallet policies
        - ERC-8004 reputation event (if writer configured)
        """
        severity = classify_severity(denial_reasons)
        logger.info(f"Severity classification: {severity} for agent {agent_id}")

        if severity not in ("HIGH", "CRITICAL"):
            logger.info(f"Severity {severity} below threshold — no forensic record")
            return None

        # Analyze what happened
        findings = _analyze_attack_vector(denial_reasons, intent_context)

        # Generate recommendations for Circle's enforcement layer
        recommendations = _generate_recommendations(severity, denial_reasons, agent_id)

        # Build trigger context
        trigger = {
            "type": "PAYMENT_DENIAL",
            "denial_receipt_hash": denial_receipt_hash,
            "denial_reasons": denial_reasons,
        }
        if intent_context:
            trigger["intent_context"] = intent_context

        # Sign forensic record
        record = ForensicRecord(
            record_id=f"iso-{uuid.uuid4().hex[:12]}",
            tenant=self.tenant,
            agent_id=agent_id,
            severity=severity,
            trigger=trigger,
            findings=findings,
            recommendations=recommendations,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )

        body_bytes = canonicalize(record.body_dict())
        record.receipt_hash = "sha256:" + hashlib.sha256(body_bytes).hexdigest()
        sig_bytes = self._private_key.sign(body_bytes)
        record.signature = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode("ascii")
        record.kid = self._kid

        self.records.append(record)
        logger.info(f"Forensic record created: {record.record_id}")

        # Publish reputation event to ERC-8004 registry
        if self._reputation_writer:
            try:
                finding_summary = "; ".join(f["finding"] for f in findings)
                rep_event = self._reputation_writer.publish_isolation(
                    agent_id=agent_id,
                    severity=severity,
                    isolation_id=record.record_id,
                    receipt_hash=record.receipt_hash,
                    reason=f"{severity}: {finding_summary}",
                )
                logger.info(f"ERC-8004 reputation event: {rep_event.event_id}")
            except Exception as e:
                logger.warning(f"ERC-8004 reputation publish failed: {e}")

        return record

    def correlate_across_agents(
        self,
        isolation_record: ForensicRecord,
        receipt_chain: list[dict],
    ):
        """Run cross-agent forensic correlation after an incident.

        Returns a signed CorrelationReport if the correlation engine is configured.
        """
        if not self._correlation_engine:
            return None

        denial_reasons = isolation_record.trigger.get("denial_reasons", [])
        return self._correlation_engine.correlate(
            trigger_isolation_id=isolation_record.record_id,
            trigger_agent_id=isolation_record.agent_id,
            trigger_denial_reasons=denial_reasons,
            receipt_chain=receipt_chain,
        )

    # Backward-compat helpers (dashboard checks these)
    def is_agent_revoked(self, agent_id: str) -> bool:
        """Check if we have a forensic record for this agent.

        Note: actual revocation is Circle's job via Action Gate.
        This just indicates we've documented an incident.
        """
        return any(r.agent_id == agent_id for r in self.records)

    def is_wallet_frozen(self) -> bool:
        """Check if we've recommended a wallet freeze.

        Note: actual freezing is Circle's job via wallet policies.
        This indicates we've recommended it.
        """
        for record in self.records:
            for rec in record.recommendations:
                if rec.get("action") == "REDUCE_SPENDING_LIMIT":
                    return True
        return False
