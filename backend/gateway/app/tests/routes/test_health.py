"""Gateway liveness and readiness contract tests."""
import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.rest.v1.health import _probe_service


class Connection:
    def __init__(self, ready: bool) -> None:
        self.ready = ready

    def is_connected(self) -> bool:
        return self.ready


class Admin:
    def __init__(self, state: dict[str, bool]) -> None:
        self.state = state

    def command(self, _name: str) -> dict[str, int]:
        if not self.state["mongodb"]:
            raise TimeoutError
        return {"ok": 1}


class Mongo:
    def __init__(self, state: dict[str, bool]) -> None:
        self.admin = Admin(state)


def test_dependency_failure_live_and_recovery(monkeypatch) -> None:
    import app.db.session as db_session
    import app.main as main
    import app.rest.v1.health as health_module

    state = {"mongodb": True}
    rabbitmq = Connection(True)
    monkeypatch.setattr(db_session, "get_client", lambda: Mongo(state))
    monkeypatch.setattr(main, "_rpc_client", rabbitmq)
    async def downstream_ready() -> dict[str, bool]:
        return {"rag_ready": True}
    monkeypatch.setattr(health_module, "_critical_services_ready", downstream_ready)
    client = TestClient(app)

    assert client.get("/ready").status_code == 200
    state["mongodb"] = False
    assert client.get("/ready").status_code == 503
    assert client.get("/live").status_code == 200
    state["mongodb"] = True
    assert client.get("/ready").status_code == 200


def test_detailed_probe_distinguishes_live_from_ready() -> None:
    class Response:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    class Client:
        async def get(self, url: str) -> Response:
            return Response(503 if url.endswith("/ready") else 200)

    result = asyncio.run(_probe_service(Client(), "rag", 8004))
    assert result == {
        "name": "rag",
        "status": "degraded",
        "port": 8004,
        "live": True,
        "ready": False,
        "message": "Live but not ready for traffic",
    }
