"""Gateway boundary tests for origin, CSRF and role authorization."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_user, require_admin
from app.core.deps import get_auth_service, get_config
from app.services.auth_service import AuthenticationFailed
from shared.auth import AuthIdentity


class StubAuthService:
    def __init__(self, identity: AuthIdentity) -> None:
        self.identity = identity
        self.calls: list = []

    def authenticate_session(
        self,
        session_token,
        *,
        csrf_cookie=None,
        csrf_header=None,
        require_csrf=False,
    ):
        self.calls.append((session_token, csrf_cookie, csrf_header, require_csrf))
        if not session_token:
            raise AuthenticationFailed("Authentication required")
        if require_csrf and (not csrf_cookie or csrf_cookie != csrf_header):
            raise AuthenticationFailed("CSRF validation failed")
        return self.identity, {"user_id": self.identity.user_id, "role": self.identity.role}


def _app(identity: AuthIdentity):
    service = StubAuthService(identity)
    config = SimpleNamespace(
        cors_origins_list=["https://app.example.test"],
        session_cookie_name="ragapp_session",
        csrf_cookie_name="ragapp_csrf",
    )
    app = FastAPI()
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_config] = lambda: config

    @app.get("/me")
    async def me(current: AuthIdentity = Depends(get_current_user)):
        return current.to_dict()

    @app.post("/change")
    async def change(current: AuthIdentity = Depends(get_current_user)):
        return current.to_dict()

    @app.get("/admin")
    async def admin(current: AuthIdentity = Depends(require_admin)):
        return current.to_dict()

    return app, service


def _identity(role: str) -> AuthIdentity:
    return AuthIdentity(
        tenant_id="tenant-a",
        user_id=f"{role}-a",
        role=role,
        admin_id="admin-a",
    )


def test_regular_user_is_forbidden_from_admin_endpoint() -> None:
    app, _service = _app(_identity("user"))
    with TestClient(app) as client:
        response = client.get("/admin", cookies={"ragapp_session": "session"})
    assert response.status_code == 403


def test_admin_is_allowed_on_admin_endpoint() -> None:
    app, _service = _app(_identity("admin"))
    with TestClient(app) as client:
        response = client.get("/admin", cookies={"ragapp_session": "session"})
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_unsafe_request_requires_matching_double_submit_csrf_token() -> None:
    app, service = _app(_identity("user"))
    with TestClient(app) as client:
        denied = client.post("/change", cookies={"ragapp_session": "session", "ragapp_csrf": "one"})
        allowed = client.post(
            "/change",
            cookies={"ragapp_session": "session", "ragapp_csrf": "one"},
            headers={"x-csrf-token": "one"},
        )

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert service.calls[-1][-1] is True


def test_untrusted_browser_origin_is_rejected_before_authentication() -> None:
    app, service = _app(_identity("admin"))
    with TestClient(app) as client:
        response = client.get(
            "/admin",
            cookies={"ragapp_session": "session"},
            headers={"origin": "https://evil.example"},
        )

    assert response.status_code == 403
    assert service.calls == []
