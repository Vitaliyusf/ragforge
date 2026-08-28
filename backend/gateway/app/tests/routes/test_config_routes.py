"""Contract tests for the deployment-owned configuration route."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import require_admin
from app.core.deps import get_config_management_service
from app.rest.v1 import config as config_routes
from shared.auth import AuthIdentity


class DummyConfigManagementService:
    def __init__(self):
        self.calls = []

    async def get_config(self):
        self.calls.append("get_config")
        return {
            "llm_implementation": "vllm",
            "configuration_policy": {"owner": "deployment", "live_effective": []},
        }


def build_app(service):
    app = FastAPI()
    app.include_router(config_routes.router, prefix="/v1")
    app.dependency_overrides[get_config_management_service] = lambda: service
    app.dependency_overrides[require_admin] = lambda: AuthIdentity(
        tenant_id="tenant-a", user_id="admin-a", role="admin", admin_id="admin-a"
    )
    return app


def test_get_config_exposes_effective_deployment_config():
    service = DummyConfigManagementService()

    with TestClient(build_app(service)) as client:
        response = client.get("/v1/config")

    assert response.status_code == 200
    assert response.json()["configuration_policy"]["owner"] == "deployment"
    assert service.calls == ["get_config"]


def test_config_writes_are_not_routable():
    service = DummyConfigManagementService()

    with TestClient(build_app(service)) as client:
        response = client.post("/v1/config", json={"unknown_field": "ignored-before-config-01"})

    assert response.status_code == 405
    assert service.calls == []
