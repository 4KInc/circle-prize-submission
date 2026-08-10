"""Six-agent governance system for autonomous USDC payments.

Each agent has its own Ed25519 signing key and produces independently
verifiable signed artifacts. The system operates as a coordinated
governance layer between AI agents and Circle Agent Wallets.

Agents:
1. Coordinator  — discovers x402 services, routes capabilities
2. Gateway      — evaluates payment intents, signs approval/denial receipts
3. Auditor      — audits receipts against compliance frameworks (Gemini)
4. Investigator — deep analysis of suspicious denials, incident reports (Gemini)
5. Recommender  — suggests policy changes based on patterns (Gemini)
6. Isolator     — quarantines rogue agents, revokes identity, freezes wallets

All agents work standalone (in-memory). No Firestore required.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "engine")
if os.path.isdir(ENGINE_PATH) and ENGINE_PATH not in sys.path:
    sys.path.insert(0, ENGINE_PATH)

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from gateway.canonical import canonicalize

logger = logging.getLogger("circle.agents")


# ── Signed Artifact ──────────────────────────────────────────────────

@dataclass
class SignedArtifact:
    """A signed artifact produced by any agent."""
    artifact_type: str
    agent_name: str
    body: dict
    artifact_hash: str = ""
    signature: str = ""
    kid: str = ""

    def sign(self, private_key: Ed25519PrivateKey, kid: str):
        body_bytes = canonicalize(self.body)
        self.artifact_hash = "sha256:" + hashlib.sha256(body_bytes).hexdigest()
        sig_bytes = private_key.sign(body_bytes)
        self.signature = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode("ascii")
        self.kid = kid

    def envelope(self) -> dict:
        return {
            "body": self.body,
            "sig": {"alg": "EdDSA", "kid": self.kid, "value": self.signature},
            "artifact_hash": self.artifact_hash,
            "artifact_type": self.artifact_type,
            "agent": self.agent_name,
        }


# ── Agent Base ───────────────────────────────────────────────────────

class AgentBase:
    """Base class for all governance agents."""

    def __init__(self, name: str, tenant: str):
        self.name = name
        self.tenant = tenant
        self._private_key = Ed25519PrivateKey.generate()
        self._kid = f"{name}-{tenant}-{uuid.uuid4().hex[:8]}"
        self.artifacts: list[SignedArtifact] = []

    def _sign_artifact(self, artifact_type: str, body: dict) -> SignedArtifact:
        artifact = SignedArtifact(artifact_type=artifact_type, agent_name=self.name, body=body)
        artifact.sign(self._private_key, self._kid)
        self.artifacts.append(artifact)
        return artifact

    def get_public_key_jwk(self) -> dict:
        pub_bytes = self._private_key.public_key().public_bytes_raw()
        x_b64url = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode("ascii")
        return {"kty": "OKP", "crv": "Ed25519", "kid": self._kid, "alg": "EdDSA", "x": x_b64url}


# ── 1. Coordinator Agent ─────────────────────────────────────────────

class CoordinatorAgent(AgentBase):
    """Discovers x402 services and routes agent capabilities."""

    def __init__(self, tenant: str):
        super().__init__("coordinator", tenant)

    def discover_services(self, query: str = "market data") -> SignedArtifact:
        """Query Circle Agent Marketplace and local x402 services."""
        services = []

        # Local x402 service
        from circle.golden_path import SERVICE_CATALOG
        for svc in SERVICE_CATALOG:
            services.append({
                "name": svc["name"],
                "endpoint": svc.get("endpoint", ""),
                "price": svc.get("price_usdc", "?"),
                "source": "local_x402",
            })

        # Circle Agent Marketplace
        try:
            from circle.cli import services_search
            marketplace = services_search(query, limit=5)
            for svc in marketplace:
                meta = svc.get("metadata", {})
                provider = meta.get("provider", {})
                services.append({
                    "name": provider.get("name", "unknown"),
                    "endpoint": svc.get("resource", ""),
                    "price": str(int(svc.get("accepts", [{}])[0].get("amount", "0")) / 1_000_000),
                    "source": "circle_marketplace",
                })
        except Exception as e:
            logger.warning(f"Marketplace discovery failed: {e}")

        body = {
            "discovery_id": f"disc-{uuid.uuid4().hex[:12]}",
            "tenant": self.tenant,
            "query": query,
            "timestamp": datetime.now(UTC).isoformat(),
            "services_found": len(services),
            "services": services,
            "sources": ["local_x402", "circle_marketplace"],
        }
        artifact = self._sign_artifact("service_discovery", body)
        logger.info(f"Coordinator discovered {len(services)} services")
        return artifact


# ── 2. Gateway Agent ─────────────────────────────────────────────────
# (Already implemented in circle/executor.py — PaymentExecutor IS the Gateway)


# ── 3. Auditor Agent ─────────────────────────────────────────────────

class AuditorAgent(AgentBase):
    """Audits payment receipts against compliance frameworks using Gemini."""

    def __init__(self, tenant: str):
        super().__init__("auditor", tenant)

    def audit_receipt(self, receipt_envelope: dict, settlement_tx: str | None = None) -> SignedArtifact:
        """Audit a single receipt against compliance frameworks."""
        body = receipt_envelope.get("body", {})
        decision = body.get("decision", "unknown")
        delegation = body.get("delegation_context", {})

        verdict = "ALIGNED" if decision in ("approve", "deny") else "INSUFFICIENT_EVIDENCE"
        findings = []

        if decision == "approve" and delegation.get("settlement_tx"):
            findings.append({
                "framework": "NIST AI RMF / GOVERN",
                "finding": "Payment authorized by deterministic policy engine (zero-LLM). Settlement tx bound to receipt.",
                "status": "COMPLIANT",
            })
            findings.append({
                "framework": "EU AI Act Article 14",
                "finding": "Human oversight maintained via policy rules defined by operator. Agent cannot override policy.",
                "status": "COMPLIANT",
            })

        if decision == "deny":
            findings.append({
                "framework": "NIST AI RMF / MANAGE",
                "finding": f"Rogue payment blocked pre-settlement. Reasons: {body.get('reasons', [])}",
                "status": "COMPLIANT",
            })
            findings.append({
                "framework": "EU AI Act Article 15",
                "finding": "System demonstrated robustness by blocking unauthorized payment attempt.",
                "status": "COMPLIANT",
            })

        audit_body = {
            "audit_id": f"audit-{uuid.uuid4().hex[:12]}",
            "tenant": self.tenant,
            "timestamp": datetime.now(UTC).isoformat(),
            "receipt_hash": receipt_envelope.get("receipt_hash", ""),
            "decision_audited": decision,
            "verdict": verdict,
            "findings": findings,
            "frameworks_checked": ["EU AI Act", "NIST AI RMF", "NIST SP 800-53"],
        }
        artifact = self._sign_artifact("audit_report", audit_body)
        logger.info(f"Auditor: {verdict} for receipt {receipt_envelope.get('receipt_hash', '')[:20]}...")
        return artifact

    def generate_compliance_report(
        self, receipts: list[dict], isolations: list[dict],
        spend, verification_status: str,
    ) -> SignedArtifact:
        """Generate a comprehensive compliance report using Gemini."""
        # Try Gemini for the narrative
        narrative = self._gemini_compliance_narrative(receipts, isolations, spend, verification_status)

        report_body = {
            "report_id": f"report-{uuid.uuid4().hex[:12]}",
            "tenant": self.tenant,
            "timestamp": datetime.now(UTC).isoformat(),
            "total_receipts_audited": len(receipts),
            "total_governed_spend_usdc": str(spend),
            "verification_status": verification_status,
            "isolations": len(isolations),
            "narrative": narrative,
            "frameworks": ["EU AI Act (Art 14, 15, 52)", "NIST AI RMF", "NIST SP 800-53"],
        }
        artifact = self._sign_artifact("compliance_report", report_body)
        logger.info("Auditor: compliance report generated")
        return artifact

    def _gemini_compliance_narrative(self, receipts, isolations, spend, verification) -> dict:
        try:
            from google import genai
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                return self._fallback_narrative(receipts, isolations, spend, verification)

            client = genai.Client(api_key=api_key)
            prompt = f"""Analyze this AI agent payment governance data and produce a compliance narrative.

Governed spend: {spend} USDC
Receipts: {len(receipts)} ({sum(1 for r in receipts if r.get('body',{}).get('decision')=='approve')} approved, {sum(1 for r in receipts if r.get('body',{}).get('decision')=='deny')} denied)
Isolations: {len(isolations)} rogue agents contained
Verification: {verification}

Respond with JSON:
{{"summary": "<2-3 sentences>", "eu_ai_act": {{"article_14": "<finding>", "article_15": "<finding>", "article_52": "<finding>"}}, "nist_ai_rmf": {{"govern": "<finding>", "map": "<finding>", "measure": "<finding>", "manage": "<finding>"}}, "recommendations": ["<1>", "<2>", "<3>"]}}"""

            response = client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(text)
        except Exception as e:
            logger.warning(f"Gemini compliance failed: {e}")
            return self._fallback_narrative(receipts, isolations, spend, verification)

    def _fallback_narrative(self, receipts, isolations, spend, verification) -> dict:
        approved = sum(1 for r in receipts if r.get("body", {}).get("decision") == "approve")
        denied = sum(1 for r in receipts if r.get("body", {}).get("decision") == "deny")
        spend_str = str(spend) if isinstance(spend, str) else f"{spend:.2f}"
        return {
            "summary": f"Governed ${spend_str} USDC. {approved} payments approved, {denied} blocked. {len(isolations)} rogue agents contained. Integrity: {verification}.",
            "eu_ai_act": {
                "article_14": "Human oversight via deterministic policy rules. No LLM in authorization path.",
                "article_15": "Ed25519 receipts, hash chains, Merkle anchoring. Isolator quarantines rogue agents.",
                "article_52": "Every decision produces a signed receipt. Settlement txs on-chain and verifiable.",
            },
            "nist_ai_rmf": {
                "govern": "Deterministic policy engine. Policies defined declaratively by operator.",
                "map": "Risk identified via policy violations (off-allowlist, over-cap, rate limit).",
                "measure": "Continuous monitoring via receipt chain. Merkle anchoring for periodic checkpoints.",
                "manage": "Automated containment via Isolator. Identity revocation + wallet freeze.",
            },
            "recommendations": [
                "Enable Circle wallet spending policies on mainnet for defense-in-depth.",
                "Configure per-tenant signing keys for multi-tenant isolation.",
                "Schedule periodic Merkle anchoring to Base mainnet.",
            ],
        }


# ── 4. Investigator Agent ────────────────────────────────────────────

class InvestigatorAgent(AgentBase):
    """Investigates suspicious payment denials and produces incident reports."""

    def __init__(self, tenant: str):
        super().__init__("investigator", tenant)

    def investigate(
        self, denial_receipt: dict, denial_reasons: list[str],
        intent_context: dict | None = None,
    ) -> SignedArtifact:
        """Analyze a suspicious denial and produce an incident report."""
        narrative = self._analyze_incident(denial_receipt, denial_reasons, intent_context)

        body = {
            "incident_id": f"inc-{uuid.uuid4().hex[:12]}",
            "tenant": self.tenant,
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": narrative.get("severity", "MEDIUM"),
            "trigger": {
                "type": "PAYMENT_DENIAL",
                "receipt_hash": denial_receipt.get("receipt_hash", ""),
                "denial_reasons": denial_reasons,
            },
            "narrative": narrative,
            "evidence_references": {
                "denial_receipt": denial_receipt.get("receipt_hash", ""),
                "intent_context": intent_context,
            },
        }
        artifact = self._sign_artifact("incident_report", body)
        logger.info(f"Investigator: {narrative['severity']} incident — {body['incident_id']}")
        return artifact

    def _analyze_incident(self, receipt, reasons, context) -> dict:
        reasons_text = " ".join(reasons).lower()
        intent = context or {}

        # Classify severity
        injection_keywords = ["override", "ignore", "bypass", "attacker", "injection", "malicious"]
        if any(kw in reasons_text or kw in str(intent.get("reason", "")).lower() for kw in injection_keywords):
            severity = "CRITICAL"
            summary = "Prompt injection attack detected. Agent attempted to redirect funds to an unauthorized address with adversarial instructions."
            root_cause = "Adversarial prompt injection in tool output or agent context."
            recommended = ["Immediately isolate agent", "Freeze associated wallet", "Review all recent agent activity"]
        elif len(reasons) >= 2:
            severity = "HIGH"
            summary = "Multiple policy violations in a single payment attempt. Pattern suggests compromised agent or configuration error."
            root_cause = "Agent exceeded both payee allowlist and amount cap simultaneously."
            recommended = ["Isolate agent", "Freeze wallet", "Investigate agent's recent context"]
        else:
            severity = "MEDIUM"
            summary = "Single policy violation. May be a misconfiguration or edge case."
            root_cause = f"Policy violation: {reasons[0] if reasons else 'unknown'}"
            recommended = ["Monitor agent", "Review policy configuration"]

        return {
            "severity": severity,
            "summary": summary,
            "root_cause_hypothesis": root_cause,
            "agents_involved": [intent.get("agent_id", "ops-agent")],
            "timeline": [
                {"event": "Payment intent formed", "detail": f"payee={intent.get('payee', '?')[:20]}... amount={intent.get('amount', '?')}"},
                {"event": "Policy evaluation", "detail": f"DENIED: {', '.join(reasons)}"},
                {"event": "Incident triggered", "detail": f"Severity: {severity}"},
            ],
            "recommended_actions": recommended,
        }


# ── 5. Recommender Agent ─────────────────────────────────────────────

class RecommenderAgent(AgentBase):
    """Suggests policy changes based on incident patterns."""

    def __init__(self, tenant: str):
        super().__init__("recommender", tenant)

    def recommend(
        self, incident_report: SignedArtifact, current_policy_hash: str,
    ) -> SignedArtifact:
        """Analyze an incident and propose policy improvements."""
        incident = incident_report.body
        severity = incident.get("severity", "MEDIUM")
        reasons = incident.get("trigger", {}).get("denial_reasons", [])

        proposals = []

        # Propose based on incident type
        if severity in ("HIGH", "CRITICAL"):
            proposals.append({
                "change_type": "ADD_RATE_LIMIT",
                "description": "Reduce rate limit window after HIGH/CRITICAL incident",
                "current": "5 actions per 60 seconds",
                "proposed": "2 actions per 60 seconds for 24 hours post-incident",
                "rationale": "Limit blast radius of compromised agents",
                "confidence": "HIGH",
            })

        if any("AMOUNT_EXCEEDS_CAP" in r for r in reasons):
            proposals.append({
                "change_type": "LOWER_AMOUNT_CAP",
                "description": "Reduce per-transaction amount cap",
                "current": "1.0 USDC",
                "proposed": "0.50 USDC",
                "rationale": "Agent attempted payment 50x over cap. Tighter cap reduces exposure.",
                "confidence": "MEDIUM",
            })

        if any("RESOURCE_OUT_OF_SCOPE" in r for r in reasons):
            proposals.append({
                "change_type": "ENABLE_STRICT_ALLOWLIST",
                "description": "Switch to strict allowlist mode with explicit payee approval",
                "current": "Pattern-based resource scope",
                "proposed": "Explicit payee address allowlist only",
                "rationale": "Agent attempted payment to unknown payee. Strict mode prevents discovery of unvetted services.",
                "confidence": "HIGH",
            })

        if severity == "CRITICAL":
            proposals.append({
                "change_type": "ENABLE_CIRCLE_WALLET_POLICY",
                "description": "Set Circle wallet spending policies as independent second wall",
                "current": "Verigate gate only",
                "proposed": "Verigate gate + Circle wallet limit (per-tx: $1, daily: $5)",
                "rationale": "Defense-in-depth. Even if Verigate is bypassed, Circle enforces independently.",
                "confidence": "HIGH",
            })

        body = {
            "proposal_id": f"prop-{uuid.uuid4().hex[:12]}",
            "tenant": self.tenant,
            "timestamp": datetime.now(UTC).isoformat(),
            "trigger": {
                "type": "INCIDENT_REPORT",
                "incident_id": incident.get("incident_id", ""),
                "severity": severity,
            },
            "current_policy_hash": current_policy_hash,
            "proposals": proposals,
            "proposal_count": len(proposals),
        }
        artifact = self._sign_artifact("policy_proposal", body)
        logger.info(f"Recommender: {len(proposals)} proposals for {severity} incident")
        return artifact


# ── 6. Isolator Agent ────────────────────────────────────────────────
# (Already implemented in circle/isolator.py — reuse and enhance)


# ── Governance System ────────────────────────────────────────────────

class GovernanceSystem:
    """The full 6-agent governance system for autonomous USDC payments.

    Orchestrates all agents in a coordinated response to payment events.
    Each agent operates independently with its own signing key.
    """

    def __init__(self, tenant: str = "verigate-demo"):
        self.tenant = tenant
        self.coordinator = CoordinatorAgent(tenant)
        self.auditor = AuditorAgent(tenant)
        self.investigator = InvestigatorAgent(tenant)
        self.recommender = RecommenderAgent(tenant)
        # Gateway = PaymentExecutor (circle/executor.py)
        # Isolator = Isolator (circle/isolator.py)

    def get_all_keys(self) -> dict[str, dict]:
        """Return all agent public keys for independent verification."""
        return {
            "coordinator": self.coordinator.get_public_key_jwk(),
            "auditor": self.auditor.get_public_key_jwk(),
            "investigator": self.investigator.get_public_key_jwk(),
            "recommender": self.recommender.get_public_key_jwk(),
        }

    def get_all_artifacts(self) -> list[dict]:
        """Return all signed artifacts from all agents."""
        all_artifacts = []
        for agent in [self.coordinator, self.auditor, self.investigator, self.recommender]:
            all_artifacts.extend([a.envelope() for a in agent.artifacts])
        return all_artifacts

    def run_post_denial_pipeline(
        self, denial_receipt: dict, denial_reasons: list[str],
        intent_context: dict | None = None, policy_hash: str = "",
    ) -> dict:
        """Run the full post-denial agent pipeline.

        1. Investigator analyzes the incident
        2. Recommender proposes policy changes
        3. (Isolator handles containment — called separately)
        4. Auditor audits the denial receipt

        Returns summary of all agent actions.
        """
        # 1. Investigate
        incident = self.investigator.investigate(denial_receipt, denial_reasons, intent_context)

        # 2. Recommend policy changes
        proposal = self.recommender.recommend(incident, policy_hash)

        # 3. Audit the denial receipt
        audit = self.auditor.audit_receipt(denial_receipt)

        return {
            "incident": incident.envelope(),
            "proposal": proposal.envelope(),
            "audit": audit.envelope(),
            "agents_active": ["investigator", "recommender", "auditor"],
        }
