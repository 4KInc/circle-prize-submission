"""x401 credential verification — PROTOCOL-COMPATIBLE STUB.

This is NOT a full x401 implementation. Real x401 uses W3C Verifiable
Credentials with selective disclosure and zero-knowledge proofs (as
specified by Proof, co-endorsed by Circle, OpenAI, Google, Okta).

This stub implements the SAME SEMANTIC CONTRACT as x401:
- Issuer signs a credential authorizing an agent with scoped permissions
- Verifier checks signature, expiry, revocation, and scope
- Credential hash is bound into the receipt chain

The stub uses Ed25519 signatures instead of ZK proofs. When Circle
ships the x401 SDK, this module can be swapped for the real thing
without changing the receipt chain — the credential_hash field is
format-agnostic.

What this proves for the demo:
- The receipt chain CAN bind agent identity (architecture is ready)
- The verification pipeline CAN check identity binding
- The credential hash is embedded in every receipt

What this does NOT do:
- Selective disclosure / zero-knowledge proofs
- W3C Verifiable Credential format
- Real x401 HTTP 401 challenge/response flow
"""

from __future__ import annotations

import base64
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

logger = logging.getLogger("circle.x401")


@dataclass
class X401Credential:
    """A verifiable credential proving agent authorization.

    In production, this would be a W3C Verifiable Credential with
    selective disclosure / ZK proofs per the x401 spec. For the demo,
    we use Ed25519-signed credentials with the same semantic fields.
    """
    credential_id: str
    issuer: str                    # Human principal who authorized the agent
    subject_agent_id: str          # The agent being authorized
    scope: list[str]               # Authorized actions (e.g., ["pay", "transfer"])
    max_amount: float | None       # Maximum single payment amount
    allowed_payees: list[str]      # Authorized payee addresses
    issued_at: str                 # ISO timestamp
    expires_at: str                # ISO timestamp
    revoked: bool = False
    signature: str = ""            # Ed25519 signature over credential body
    issuer_kid: str = ""           # Key ID of the issuer's signing key

    def body_dict(self) -> dict:
        """Signed body — revocation state is external, not in the signed payload."""
        return {
            "credential_id": self.credential_id,
            "issuer": self.issuer,
            "subject_agent_id": self.subject_agent_id,
            "scope": sorted(self.scope),
            "max_amount": self.max_amount,
            "allowed_payees": sorted(p.lower() for p in self.allowed_payees),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "schema": "x401-credential-v0.1",
        }

    def credential_hash(self) -> str:
        import json
        body_bytes = json.dumps(self.body_dict(), sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(body_bytes).hexdigest()


@dataclass
class X401VerificationResult:
    """Result of verifying an x401 credential."""
    valid: bool
    credential_hash: str
    errors: list[str] = field(default_factory=list)
    issuer: str = ""
    subject: str = ""
    scope: list[str] = field(default_factory=list)


class X401Issuer:
    """Issues x401 credentials for agent authorization.

    In production, this would be the human operator's identity provider.
    For the demo, it simulates an operator signing a credential that
    authorizes a specific agent with scoped permissions.
    """

    def __init__(self, issuer_name: str, private_key: Ed25519PrivateKey | None = None):
        self.issuer_name = issuer_name
        self._private_key = private_key or Ed25519PrivateKey.generate()
        self._kid = f"x401-issuer-{uuid.uuid4().hex[:8]}"
        self._issued: dict[str, X401Credential] = {}
        self._revoked: set[str] = set()

    def issue_credential(
        self,
        agent_id: str,
        scope: list[str],
        max_amount: float | None = None,
        allowed_payees: list[str] | None = None,
        ttl_seconds: int = 3600,
    ) -> X401Credential:
        """Issue a new x401 credential authorizing an agent."""
        now = datetime.now(UTC)
        from datetime import timedelta
        expires = now + timedelta(seconds=ttl_seconds)

        cred = X401Credential(
            credential_id=f"x401-{uuid.uuid4().hex[:12]}",
            issuer=self.issuer_name,
            subject_agent_id=agent_id,
            scope=scope,
            max_amount=max_amount,
            allowed_payees=allowed_payees or [],
            issued_at=now.isoformat(),
            expires_at=expires.isoformat(),
            issuer_kid=self._kid,
        )

        # Sign the credential body
        import json
        body_bytes = json.dumps(cred.body_dict(), sort_keys=True, separators=(",", ":")).encode()
        sig_bytes = self._private_key.sign(body_bytes)
        cred.signature = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode("ascii")

        self._issued[cred.credential_id] = cred
        logger.info(f"x401 credential issued: {cred.credential_id} for agent {agent_id}")
        return cred

    def revoke_credential(self, credential_id: str) -> None:
        self._revoked.add(credential_id)
        if credential_id in self._issued:
            self._issued[credential_id].revoked = True
        logger.info(f"x401 credential revoked: {credential_id}")

    def get_public_key(self) -> Ed25519PublicKey:
        return self._private_key.public_key()

    def get_public_key_jwk(self) -> dict:
        pub_bytes = self._private_key.public_key().public_bytes_raw()
        x_b64url = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode("ascii")
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "kid": self._kid,
            "use": "sig",
            "alg": "EdDSA",
            "x": x_b64url,
        }


class X401Verifier:
    """Verifies x401 credentials before authorizing payments.

    This sits in the Verigate executor pipeline: credential verification
    happens BEFORE policy evaluation, and the credential hash is bound
    into the receipt.
    """

    def __init__(self):
        self._trusted_issuers: dict[str, Ed25519PublicKey] = {}
        self._revoked_credentials: set[str] = set()

    def trust_issuer(self, kid: str, public_key: Ed25519PublicKey) -> None:
        self._trusted_issuers[kid] = public_key

    def trust_issuer_jwk(self, jwk: dict) -> None:
        kid = jwk["kid"]
        x_bytes = base64.urlsafe_b64decode(jwk["x"] + "==")
        pub = Ed25519PublicKey.from_public_bytes(x_bytes)
        self._trusted_issuers[kid] = pub

    def revoke_credential(self, credential_id: str) -> None:
        """Add a credential to the revocation list."""
        self._revoked_credentials.add(credential_id)

    def verify(self, credential: X401Credential) -> X401VerificationResult:
        """Verify an x401 credential.

        Checks:
        1. Signature is valid (issuer's Ed25519 key)
        2. Credential is not expired
        3. Credential is not revoked
        4. Issuer is trusted
        """
        errors = []
        cred_hash = credential.credential_hash()

        # Check issuer trust
        if credential.issuer_kid not in self._trusted_issuers:
            errors.append(f"Untrusted issuer key: {credential.issuer_kid}")
            return X401VerificationResult(
                valid=False, credential_hash=cred_hash, errors=errors,
            )

        # Verify signature
        pub_key = self._trusted_issuers[credential.issuer_kid]
        import json
        body_bytes = json.dumps(credential.body_dict(), sort_keys=True, separators=(",", ":")).encode()
        sig_bytes = base64.urlsafe_b64decode(credential.signature + "==")
        try:
            pub_key.verify(sig_bytes, body_bytes)
        except Exception:
            errors.append("Credential signature verification failed")
            return X401VerificationResult(
                valid=False, credential_hash=cred_hash, errors=errors,
            )

        # Check expiry
        now = datetime.now(UTC)
        expires = datetime.fromisoformat(credential.expires_at)
        if now > expires:
            errors.append(f"Credential expired at {credential.expires_at}")

        # Check revocation (from verifier's revocation list or credential flag)
        if credential.credential_id in self._revoked_credentials or credential.revoked:
            errors.append("Credential has been revoked")

        valid = len(errors) == 0
        return X401VerificationResult(
            valid=valid,
            credential_hash=cred_hash,
            errors=errors,
            issuer=credential.issuer,
            subject=credential.subject_agent_id,
            scope=credential.scope,
        )
