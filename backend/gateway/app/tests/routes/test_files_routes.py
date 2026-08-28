"""Tests for the new file routes."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rest.v1 import files as files_routes
from app.core.auth import get_current_user, require_admin
from app.core.deps import get_file_service
from shared.auth import AuthIdentity


class DummyFileService:
    """File service stub for route tests."""

    def __init__(self) -> None:
        self.calls: list = []

    async def get_review_case(self, file_id):
        self.calls.append(("get_review_case", file_id))
        return {"case_id": "case-1", "request_id": "req-1", "trace_id": "trace-1"}

    async def submit_review_decision(self, file_id, decision):
        self.calls.append(("submit_review_decision", file_id, decision))
        return {"status": "accepted", "request_id": "req-1", "trace_id": "trace-1"}

    async def list_own_files(self):
        self.calls.append(("list_own_files",))
        return {"files": [], "request_id": "req-1", "trace_id": "trace-1"}

    async def get_audit_trail(self, file_id, *, cursor=None, limit=50):
        self.calls.append(("get_audit_trail", file_id, cursor, limit))
        return {"events": [], "request_id": "req-1", "trace_id": "trace-1"}


def build_app(service):
    """Create a small app around the files router."""
    app = FastAPI()
    app.include_router(files_routes.router, prefix="/v1")
    app.dependency_overrides[get_file_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: AuthIdentity(
        tenant_id="tenant-a",
        user_id="admin-a",
        role="admin",
        admin_id="admin-a",
    )
    return app


def test_review_case_route_calls_service():
    """Review-case route should delegate to FileService only."""
    service = DummyFileService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.get("/v1/files/file-123/review-case")

    assert response.status_code == 200
    assert response.json()["case_id"] == "case-1"
    assert service.calls == [("get_review_case", "file-123")]


def test_review_decision_route_validates_and_calls_service():
    """Review-decision route should validate body and call the service."""
    service = DummyFileService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/files/file-123/review-decision",
            json={
                "decision": "accept_as_is",
                "review_case_id": "case-1",
                "notes": "looks good",
                "based_on_text_hash": "hash-123",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert service.calls == [
        (
            "submit_review_decision",
            "file-123",
            {
                "decision": "accept_as_is",
                "review_case_id": "case-1",
                "notes": "looks good",
                "based_on_text_hash": "hash-123",
                "reviewer": "admin-a",
                "reviewer_role": "admin",
            },
        )
    ]


def test_review_decision_route_rejects_missing_decision():
    """Schema validation should reject an empty decision payload."""
    service = DummyFileService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.post("/v1/files/file-123/review-decision", json={"notes": "missing decision"})

    assert response.status_code == 422


def test_review_decision_route_rejects_unsupported_decision():
    """Schema validation should enforce the shared human decision contract."""
    service = DummyFileService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/files/file-123/review-decision",
            json={"decision": "approve", "notes": "unsupported"},
        )

    assert response.status_code == 422


def test_review_decision_rejects_client_supplied_reviewer_identity():
    """The authenticated server identity is the only valid reviewer source."""
    service = DummyFileService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/files/file-123/review-decision",
            json={
                "review_case_id": "case-1",
                "decision": "accept_as_is",
                "reviewer": "forged-admin",
            },
        )

    assert response.status_code == 422
    assert service.calls == []


def test_regular_user_cannot_open_file_review_case():
    service = DummyFileService()
    app = FastAPI()
    app.include_router(files_routes.router, prefix="/v1")
    app.dependency_overrides[get_file_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: AuthIdentity(
        tenant_id="tenant-a",
        user_id="user-a",
        role="user",
        admin_id="admin-a",
    )

    with TestClient(app) as client:
        response = client.get("/v1/files/file-123/review-case")

    assert response.status_code == 403
    assert service.calls == []


def test_audit_trail_route_calls_service():
    """Audit-trail route should delegate to FileService only."""
    service = DummyFileService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.get("/v1/files/file-123/audit-trail?cursor=event-9&limit=25")

    assert response.status_code == 200
    assert response.json()["events"] == []
    assert service.calls == [("get_audit_trail", "file-123", "event-9", 25)]


def test_own_files_route_is_available_to_non_admin_users():
    """Uploaders must be able to list their own files without the admin role."""
    service = DummyFileService()
    app = build_app(service)
    app.dependency_overrides[get_current_user] = lambda: AuthIdentity(
        tenant_id="tenant-a",
        user_id="user-a",
        role="user",
        admin_id="admin-a",
    )

    with TestClient(app) as client:
        response = client.get("/v1/files/mine")

    assert response.status_code == 200
    assert response.json()["files"] == []
    assert service.calls == [("list_own_files",)]
