"""Memory runtime liveness and readiness contract tests."""
from app.bootstrap.runtime import MemoryApplicationRuntime


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
    import app.bootstrap.runtime as runtime_module

    state = {"mongodb": True, "rabbitmq": True}
    runtime = MemoryApplicationRuntime()
    monkeypatch.setattr(runtime_module, "get_client", lambda: Mongo(state))
    monkeypatch.setattr(runtime.consumer, "is_connected", lambda: state["rabbitmq"])

    payload, ready = runtime.readiness_payload()
    assert ready is True
    assert payload["status"] == "ready"
    state["rabbitmq"] = False
    payload, ready = runtime.readiness_payload()
    assert ready is False
    assert payload["status"] == "not_ready"
    assert runtime.live_payload()["status"] == "live"
    state["rabbitmq"] = True
    assert runtime.readiness_payload()[1] is True
