"""Shared authentication primitives used at service trust boundaries.

The public session token is opaque and is only interpreted by the gateway.
Downstream services receive a short-lived, audience-bound HMAC ticket instead
of a browser credential.  This keeps client-controlled identity fields out of
the authorization path.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional

from .context import get_context


ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_SERVICE = "service"
VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_USER, ROLE_SERVICE})
PASSWORD_SCHEME = "pbkdf2_sha256"
DEFAULT_PASSWORD_ITERATIONS = 600_000
MINIMUM_SECRET_BYTES = 32


class AuthError(ValueError):
    """Raised when credentials or a signed identity context are invalid."""

    def __init__(self, message: str, *, code: str = "internal_auth_invalid") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AuthIdentity:
    tenant_id: str
    user_id: str
    role: str
    email: Optional[str] = None
    admin_id: Optional[str] = None
    session_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.user_id:
            raise AuthError("tenant_id and user_id are required")
        if self.role not in VALID_ROLES:
            raise AuthError(f"unsupported role: {self.role}")

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_service(self) -> bool:
        return self.role == ROLE_SERVICE

    def to_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AuthIdentity":
        return cls(
            tenant_id=str(value.get("tenant_id") or ""),
            user_id=str(value.get("user_id") or ""),
            role=str(value.get("role") or ""),
            email=str(value["email"]) if value.get("email") else None,
            admin_id=str(value["admin_id"]) if value.get("admin_id") else None,
            session_id=str(value["session_id"]) if value.get("session_id") else None,
        )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except Exception as exc:
        raise AuthError("invalid base64 encoding") from exc


def _secret_bytes(secret: str) -> bytes:
    encoded = secret.encode("utf-8")
    if len(encoded) < MINIMUM_SECRET_BYTES:
        raise AuthError("authentication secret must contain at least 32 bytes")
    return encoded


def new_opaque_token() -> str:
    """Return a cryptographically random token suitable for a session cookie."""
    return secrets.token_urlsafe(32)


def token_digest(token: str, *, pepper: str = "") -> str:
    """Hash an opaque token before persistence."""
    return hmac.new(pepper.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_password(
    password: str,
    *,
    pepper: str = "",
    iterations: int = DEFAULT_PASSWORD_ITERATIONS,
) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random 128-bit salt."""
    if not isinstance(password, str) or len(password) < 15:
        raise AuthError("password must contain at least 15 characters")
    if iterations < 100_000:
        raise AuthError("password hashing iteration count is too low")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (password + pepper).encode("utf-8"),
        salt,
        iterations,
    )
    return f"{PASSWORD_SCHEME}${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str, *, pepper: str = "") -> bool:
    """Verify a password without leaking digest comparison timing."""
    try:
        scheme, raw_iterations, raw_salt, raw_digest = encoded.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(raw_iterations)
        salt = _b64decode(raw_salt)
        expected = _b64decode(raw_digest)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            (password + pepper).encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual, expected)
    except (AuthError, TypeError, ValueError):
        return False


def sign_auth_ticket(
    identity: AuthIdentity,
    *,
    secret: str,
    audience: str,
    ttl_seconds: int = 60,
    purpose: str = "request",
    issuer: str = "ragapp-gateway",
    now: Optional[int] = None,
    extra_claims: Optional[Mapping[str, Any]] = None,
) -> str:
    """Create a compact signed identity ticket for one internal audience."""
    if not audience or ttl_seconds <= 0 or ttl_seconds > 900:
        raise AuthError("invalid ticket audience or lifetime")
    issued_at = int(time.time() if now is None else now)
    payload: Dict[str, Any] = {
        **identity.to_dict(),
        "aud": audience,
        "purpose": purpose,
        "iat": issued_at,
        "exp": issued_at + ttl_seconds,
        "jti": str(uuid.uuid4()),
        "iss": issuer,
    }
    if extra_claims:
        reserved = set(payload).intersection(extra_claims)
        if reserved:
            raise AuthError("authentication ticket claims contain reserved fields")
        payload.update(dict(extra_claims))
    encoded = _b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(_secret_bytes(secret), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64encode(signature)}"


def verify_auth_ticket(
    ticket: str,
    *,
    secret: str,
    audience: str,
    purpose: Optional[str] = None,
    now: Optional[int] = None,
    clock_skew_seconds: int = 30,
    required_claims: Optional[Mapping[str, Any]] = None,
) -> AuthIdentity:
    """Verify signature, issuer, audience, purpose and ticket lifetime."""
    try:
        encoded, raw_signature = ticket.split(".", 1)
    except (AttributeError, ValueError) as exc:
        raise AuthError("malformed authentication ticket") from exc

    expected = hmac.new(_secret_bytes(secret), encoded.encode("ascii"), hashlib.sha256).digest()
    supplied = _b64decode(raw_signature)
    if not hmac.compare_digest(expected, supplied):
        raise AuthError("invalid authentication ticket signature")

    try:
        payload = json.loads(_b64decode(encoded))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuthError("invalid authentication ticket payload") from exc
    if not isinstance(payload, dict):
        raise AuthError("invalid authentication ticket payload")

    current_time = int(time.time() if now is None else now)
    if payload.get("iss") not in {"ragapp-gateway", "ragapp-internal"} or payload.get("aud") != audience:
        raise AuthError("authentication ticket audience mismatch")
    if purpose is not None and payload.get("purpose") != purpose:
        raise AuthError("authentication ticket purpose mismatch")
    if not isinstance(payload.get("iat"), int) or not isinstance(payload.get("exp"), int):
        raise AuthError("authentication ticket has no valid lifetime")
    if payload["iat"] > current_time + clock_skew_seconds:
        raise AuthError("authentication ticket is not active yet")
    if payload["exp"] <= current_time - clock_skew_seconds:
        raise AuthError(
            "authentication ticket has expired",
            code="internal_auth_expired",
        )
    for key, expected_value in (required_claims or {}).items():
        supplied_value = payload.get(key)
        if isinstance(expected_value, str) and isinstance(supplied_value, str):
            matches = hmac.compare_digest(supplied_value, expected_value)
        else:
            matches = supplied_value == expected_value
        if not matches:
            raise AuthError("authentication ticket is not bound to this request")

    return AuthIdentity.from_mapping(payload)


def internal_envelope_digest(envelope: Mapping[str, Any]) -> str:
    """Return the canonical digest covered by an internal authentication ticket."""
    signable = {key: value for key, value in envelope.items() if key != "auth_context"}
    serialized = json.dumps(
        signable,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def identity_from_context(*, required: bool = True) -> Optional[AuthIdentity]:
    """Build an identity from trusted contextvars populated at a boundary."""
    context = get_context()
    if not context.get("tenant_id") or not context.get("user_id") or not context.get("role"):
        if required:
            raise AuthError("authenticated identity is missing from request context")
        return None
    return AuthIdentity.from_mapping(context)


def verify_internal_ticket_from_envelope(
    envelope: Mapping[str, Any],
    *,
    required: Optional[bool] = None,
) -> Optional[AuthIdentity]:
    """Validate the signed context attached to a RabbitMQ/Kafka envelope."""
    auth_required = (
        os.getenv("INTERNAL_AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"}
        if required is None
        else required
    )
    ticket = envelope.get("auth_context")
    if not ticket:
        if auth_required:
            raise AuthError(
                "signed authentication context is required",
                code="internal_auth_required",
            )
        return None
    secret = os.getenv("INTERNAL_AUTH_SECRET", "")
    return verify_auth_ticket(
        str(ticket),
        secret=secret,
        audience="internal",
        purpose="request",
        required_claims={"payload_sha256": internal_envelope_digest(envelope)},
    )


def attach_internal_auth_context(
    envelope: Dict[str, Any],
    *,
    ttl_seconds: int = 300,
    identity: Optional[AuthIdentity] = None,
    secret: Optional[str] = None,
) -> Dict[str, Any]:
    """Bind a freshly signed identity to the complete outbound envelope."""
    identity = identity or identity_from_context(required=False)
    secret = secret if secret is not None else os.getenv("INTERNAL_AUTH_SECRET", "")
    required = os.getenv("INTERNAL_AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"}
    if identity is None or not secret:
        if required:
            raise AuthError("cannot publish an internal message without authenticated identity")
        return envelope
    envelope["auth_context"] = sign_auth_ticket(
        identity,
        secret=secret,
        audience="internal",
        purpose="request",
        ttl_seconds=ttl_seconds,
        issuer="ragapp-internal",
        extra_claims={"payload_sha256": internal_envelope_digest(envelope)},
    )
    return envelope
