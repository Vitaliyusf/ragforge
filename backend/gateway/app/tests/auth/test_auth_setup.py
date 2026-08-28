"""First-run administrator setup endpoint tests."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import get_auth_service, get_config
from app.rest.v1.auth import router as auth_router
from app.services.auth_service import UserConflict


class StubSetupAuthService:
    """In-memory stand-in mirroring AuthService setup semantics."""

    def __init__(self) -> None:
        self.users: list[dict] = []

    def needs_setup(self) -> bool:
        return len(self.users) == 0

    def claim_initial_admin(self, *, email: str, display_name: str, password: str) -> dict:
        if self.users:
            raise UserConflict("Setup has already been completed")
        user = {
            "user_id": "admin-1",
            "tenant_id": "default",
            "admin_id": "admin-1",
            "email": email,
            "display_name": display_name,
            "role": "admin",
            "status": "active",
            "password": password,
        }
        self.users.append(user)
        return {key: value for key, value in user.items() if key != "password"}

    def login(self, *, tenant, email, password, ip_address, user_agent):
        user = self.users[0]
        assert user["email"] == email and user["password"] == password
        public = {key: value for key, value in user.items() if key != "password"}
        return "session-token", "csrf-token", None, public


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        cors_origins_list=["https://app.example.test"],
        session_cookie_name="ragapp_session",
        csrf_cookie_name="ragapp_csrf",
        session_cookie_secure=False,
        session_cookie_samesite="lax",
        session_cookie_domain="",
        session_ttl_seconds=3600,
        bootstrap_tenant_id="default",
    )


def _client() -> tuple[TestClient, StubSetupAuthService]:
    service = StubSetupAuthService()
    app = FastAPI()
    app.include_router(auth_router, prefix="/v1")
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_config] = lambda: _config()
    return TestClient(app), service

VALID_BODY = {
    "email": "owner@example.test",
    "display_name": "Owner",
    "password": "a-long-enough-password",
}


def test_setup_status_open_on_fresh_install() -> None:
    client, _service = _client()
    response = client.get("/v1/auth/setup")
    assert response.status_code == 200
    assert response.json() == {"needs_setup": True}


def test_setup_creates_admin_and_signs_in() -> None:
    client, service = _client()
    response = client.post("/v1/auth/setup", json=VALID_BODY)
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "admin"
    assert response.cookies.get("ragapp_session") == "session-token"
    assert response.cookies.get("ragapp_csrf") == "csrf-token"
    assert response.headers["cache-control"] == "no-store"
    assert not service.needs_setup()


def test_setup_is_closed_after_first_admin() -> None:
    client, _service = _client()
    assert client.post("/v1/auth/setup", json=VALID_BODY).status_code == 201
    second = client.post(
        "/v1/auth/setup",
        json={**VALID_BODY, "email": "intruder@example.test"},
    )
    assert second.status_code == 409
    status = client.get("/v1/auth/setup")
    assert status.json() == {"needs_setup": False}


def test_setup_rejects_short_password() -> None:
    client, _service = _client()
    response = client.post(
        "/v1/auth/setup",
        json={**VALID_BODY, "password": "short"},
    )
    assert response.status_code == 422


def test_setup_rejects_untrusted_origin() -> None:
    client, _service = _client()
    response = client.post(
        "/v1/auth/setup",
        json=VALID_BODY,
        headers={"origin": "https://evil.example.test"},
    )
    assert response.status_code == 403
