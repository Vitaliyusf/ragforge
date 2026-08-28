"""Tests for the gateway long-term-memory routes."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.core.deps import get_long_term_memory_service
from app.rest.v1 import long_term_memory as memory_routes
from shared.auth import AuthIdentity


class DummyLongTermMemoryService:
    """Long-term-memory service stub for route tests."""

    def __init__(self) -> None:
        self.calls: list = []

    async def get_all_memories(self):
        self.calls.append(("get_all_memories",))
        return {"items": []}

    async def create_memory(self, content, category=None, metadata=None):
        self.calls.append(("create_memory", content, category, metadata))
        return {"status": "created"}

    async def update_memory(self, memory_id, content=None, category=None, metadata=None):
        self.calls.append(("update_memory", memory_id, content, category, metadata))
        return {"status": "updated"}

    async def delete_memory(self, memory_id):
        self.calls.append(("delete_memory", memory_id))
        return {"status": "deleted"}

    async def get_user_insight(self):
        self.calls.append(("get_user_insight",))
        return {"insight": "prefers concise answers"}

    async def update_user_insight(self, insight):
        self.calls.append(("update_user_insight", insight))
        return {"status": "updated"}


def build_app(service):
    """Create a small app around the long-term-memory router."""
    app = FastAPI()
    app.include_router(memory_routes.router, prefix="/v1")
    app.dependency_overrides[get_long_term_memory_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: AuthIdentity(
        tenant_id="tenant-a", user_id="user-a", role="user", admin_id="admin-a"
    )
    return app


def test_get_all_memories_route_calls_service():
    """List route should delegate to the long-term-memory service only."""
    service = DummyLongTermMemoryService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.get("/v1/long-term-memory")

    assert response.status_code == 200
    assert response.json() == {"items": []}
    assert service.calls == [("get_all_memories",)]


def test_create_memory_route_passes_body_values():
    """Create route should forward content, category, and metadata unchanged."""
    service = DummyLongTermMemoryService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/long-term-memory",
            json={
                "content": "Remember that the user likes summaries.",
                "category": "preference",
                "metadata": {"source": "chat"},
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "created"}
    assert service.calls == [
        (
            "create_memory",
            "Remember that the user likes summaries.",
            "preference",
            {"source": "chat"},
        )
    ]


def test_update_memory_route_passes_optional_fields():
    """Update route should preserve optional body fields when present."""
    service = DummyLongTermMemoryService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.put(
            "/v1/long-term-memory/memory-123",
            json={
                "content": "Updated memory",
                "metadata": {"confidence": 0.8},
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "updated"}
    assert service.calls == [
        ("update_memory", "memory-123", "Updated memory", None, {"confidence": 0.8})
    ]


def test_delete_memory_route_calls_service():
    """Delete route should delegate to the long-term-memory service only."""
    service = DummyLongTermMemoryService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.delete("/v1/long-term-memory/memory-456")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    assert service.calls == [("delete_memory", "memory-456")]


def test_get_user_insight_route_calls_service():
    """User-insight GET route should delegate to the long-term-memory service only."""
    service = DummyLongTermMemoryService()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.get("/v1/long-term-memory/user-insight")

    assert response.status_code == 200
    assert response.json() == {"insight": "prefers concise answers"}
    assert service.calls == [("get_user_insight",)]
