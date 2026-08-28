"""Regression tests for model-management route wiring."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import require_admin
from app.core.deps import get_model_management_service
from app.rest.v1 import models as model_routes
from shared.auth import AuthIdentity


class DummyModelManagementService:
    """ModelManagementService stub for thin route tests."""

    def __init__(self):
        self.calls: list = []

    async def list_implementations(self):
        self.calls.append("list_implementations")
        return {"implementations": [{"name": "vllm"}], "current": "vllm"}


def build_app(service):
    """Create a test app around the model-management router."""
    app = FastAPI()
    app.include_router(model_routes.router, prefix="/v1")
    app.dependency_overrides[get_model_management_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: AuthIdentity(
        tenant_id="tenant-a", user_id="admin-a", role="admin", admin_id="admin-a"
    )
    return app


def test_get_implementations_route_uses_model_management_service():
    """Gateway route should stay a thin typed-request delegator."""
    service = DummyModelManagementService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.get("/v1/model-management/implementations")

    assert response.status_code == 200
    assert response.json()["current"] == "vllm"
    assert service.calls == ["list_implementations"]
