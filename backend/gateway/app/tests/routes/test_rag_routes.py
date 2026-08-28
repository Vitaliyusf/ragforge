"""Tests for the new RAG routes."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.core.deps import get_rag_service
from app.rest.v1 import rag as rag_routes
from shared.auth import AuthIdentity


class DummyRagService:
    """RAG service stub for route tests."""

    def __init__(self) -> None:
        self.calls: list = []

    async def get_trace(self, requested_trace_id):
        self.calls.append(("get_trace", requested_trace_id))
        return {"trace": {"id": requested_trace_id}, "request_id": "req-1", "trace_id": "trace-1"}

    async def submit_feedback(self, feedback):
        self.calls.append(("submit_feedback", feedback))
        return {"status": "recorded", "request_id": "req-1", "trace_id": "trace-1"}


def build_app(service, *, role="user"):
    """Create a small app around the rag router."""
    app = FastAPI()
    app.include_router(rag_routes.router, prefix="/v1")
    app.dependency_overrides[get_rag_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: AuthIdentity(
        tenant_id="tenant-a",
        user_id="admin-a" if role == "admin" else "user-a",
        role=role,
        admin_id="admin-a",
    )
    return app


def test_trace_route_uses_requested_trace_id():
    """Trace route should pass requested_trace_id through unchanged."""
    service = DummyRagService()
    app = build_app(service, role="admin")

    with TestClient(app) as client:
        response = client.get("/v1/rag/traces/trace-123")

    assert response.status_code == 200
    assert response.json()["trace"]["id"] == "trace-123"
    assert service.calls == [("get_trace", "trace-123")]


def test_trace_route_rejects_regular_users():
    """Operational traces are admin-only even when a user knows a trace id."""
    service = DummyRagService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.get("/v1/rag/traces/trace-123")

    assert response.status_code == 403
    assert service.calls == []


def test_feedback_route_passes_payload_to_service():
    """Feedback route should remain thin and forward the request body."""
    service = DummyRagService()
    app = build_app(service)

    payload = {"score": 5, "comment": "useful answer"}
    with TestClient(app) as client:
        response = client.post("/v1/rag/feedback", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "recorded"
    assert service.calls == [("submit_feedback", payload)]
