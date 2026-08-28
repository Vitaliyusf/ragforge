"""RAG liveness and readiness contract tests."""
from fastapi.testclient import TestClient

from app.main import fastapi_app


class Dependency:
    def __init__(self, ready: bool) -> None:
        self.ready = ready

    def is_available(self) -> bool:
        return self.ready

    def is_connected(self) -> bool:
        return self.ready


def test_dependency_failure_live_and_recovery(monkeypatch) -> None:
    import app.main as main
    import app.rest.v1.health as health_module

    store = Dependency(True)
    rpc = Dependency(True)
    consumer = Dependency(True)
    monkeypatch.setattr(main, "conversation_store", store)
    monkeypatch.setattr(main, "rpc_client", rpc)
    async def downstream_ready() -> dict[str, bool]:
        return {"embedding_ready": True}
    monkeypatch.setattr(health_module, "_critical_services_ready", downstream_ready)
    fastapi_app.state.rpc_consumer = consumer
    client = TestClient(fastapi_app)

    assert client.get("/ready").status_code == 200
    rpc.ready = False
    assert client.get("/ready").status_code == 503
    assert client.get("/live").status_code == 200
    rpc.ready = True
    assert client.get("/ready").status_code == 200


def test_uninitialized_consumer_is_not_ready(monkeypatch) -> None:
    import app.rest.v1.health as health_module

    async def downstream_ready() -> dict[str, bool]:
        return {"embedding_ready": True}
    monkeypatch.setattr(health_module, "_critical_services_ready", downstream_ready)
    fastapi_app.state.rpc_consumer = None
    assert TestClient(fastapi_app).get("/ready").status_code == 503
