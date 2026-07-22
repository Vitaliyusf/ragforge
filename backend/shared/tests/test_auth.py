"""Security tests for shared authentication primitives."""
from __future__ import annotations

import pytest

from shared.auth import (
    AuthError,
    AuthIdentity,
    attach_internal_auth_context,
    hash_password,
    sign_auth_ticket,
    token_digest,
    verify_auth_ticket,
    verify_internal_ticket_from_envelope,
    verify_password,
)
from shared.context import bound_context


SECRET = "test-internal-secret-that-is-longer-than-thirty-two-bytes"


def _identity(role: str = "user") -> AuthIdentity:
    return AuthIdentity(
        tenant_id="tenant-a",
        user_id="user-a",
        role=role,
        email="user@example.com",
        admin_id="admin-a",
        session_id="session-a",
    )


def test_password_hashes_are_salted_and_verified() -> None:
    first = hash_password("correct-horse-battery-staple", pepper="pepper")
    second = hash_password("correct-horse-battery-staple", pepper="pepper")

    assert first != second
    assert verify_password("correct-horse-battery-staple", first, pepper="pepper")
    assert not verify_password("wrong-password-value", first, pepper="pepper")
    assert not verify_password("correct-horse-battery-staple", first, pepper="wrong")


def test_password_policy_and_iteration_floor_fail_closed() -> None:
    with pytest.raises(AuthError):
        hash_password("too-short")
    with pytest.raises(AuthError):
        hash_password("long-enough-password", iterations=99_999)
    assert not verify_password("anything", "not-a-supported-hash")


def test_ticket_enforces_signature_audience_purpose_and_lifetime() -> None:
    ticket = sign_auth_ticket(
        _identity(),
        secret=SECRET,
        audience="files",
        purpose="request",
        ttl_seconds=60,
        now=1_000,
    )
    verified = verify_auth_ticket(
        ticket,
        secret=SECRET,
        audience="files",
        purpose="request",
        now=1_010,
        clock_skew_seconds=0,
    )
    assert verified == _identity()

    with pytest.raises(AuthError):
        verify_auth_ticket(ticket, secret=SECRET, audience="memory", now=1_010)
    with pytest.raises(AuthError):
        verify_auth_ticket(ticket, secret=SECRET, audience="files", purpose="socket", now=1_010)
    with pytest.raises(AuthError):
        verify_auth_ticket(ticket, secret=SECRET, audience="files", now=1_060, clock_skew_seconds=0)

    encoded, signature = ticket.split(".", 1)
    replacement = "A" if signature[-1] != "A" else "B"
    with pytest.raises(AuthError):
        verify_auth_ticket(
            f"{encoded}.{signature[:-1]}{replacement}",
            secret=SECRET,
            audience="files",
            now=1_010,
        )


def test_internal_context_is_signed_from_trusted_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_REQUIRED", "true")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", SECRET)
    envelope = {"action": "test"}

    with bound_context(**_identity().to_dict()):
        result = attach_internal_auth_context(envelope, ttl_seconds=60)

    verified = verify_internal_ticket_from_envelope(result, required=True)
    assert verified is not None
    assert verified.tenant_id == "tenant-a"
    assert verified.user_id == "user-a"
    assert verified.admin_id == "admin-a"


def test_internal_context_rejects_payload_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_REQUIRED", "true")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", SECRET)
    envelope: dict = {"action": "index", "payload": {"tenant_id": "tenant-a", "value": "safe"}}

    with bound_context(**_identity().to_dict()):
        attach_internal_auth_context(envelope, ttl_seconds=60)

    envelope["payload"]["tenant_id"] = "tenant-b"
    with pytest.raises(AuthError, match="not bound"):
        verify_internal_ticket_from_envelope(envelope, required=True)


def test_required_internal_context_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_REQUIRED", "true")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", SECRET)
    with pytest.raises(AuthError):
        verify_internal_ticket_from_envelope({}, required=True)
    with pytest.raises(AuthError):
        attach_internal_auth_context({"action": "test"})


def test_opaque_token_digest_uses_pepper() -> None:
    token = "opaque-session-token"
    assert token_digest(token, pepper="a") != token_digest(token, pepper="b")
    assert token not in token_digest(token, pepper="a")
