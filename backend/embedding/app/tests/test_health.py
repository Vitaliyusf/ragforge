"""Focused tests for embedding liveness and RPC readiness semantics."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rest.v1.health import create_health_router


class ConnectionState:
    def __init__(self, connected: bool) -> None:
        self.connected = connected

    def is_connected(self) -> bool:
        return self.connected


class ModelState:
    def __init__(self, loaded: bool) -> None:
        self.loaded = loaded

    def is_loaded(self) -> bool:
        return self.loaded


def readiness_client(*, model_loaded: bool, rpc_connected: bool, kafka_connected: bool) -> TestClient:
    app = FastAPI()
    app.include_router(create_health_router(
        get_producer=lambda: ConnectionState(kafka_connected),
        get_model=lambda: ModelState(model_loaded),
        get_rpc_consumer=lambda: ConnectionState(rpc_connected),
    ))
    return TestClient(app)


def test_model_not_loaded_is_not_ready() -> None:
    response = readiness_client(
        model_loaded=False,
        rpc_connected=True,
        kafka_connected=True,
    ).get("/ready")

    assert response.status_code == 503
    assert response.json()["ready_for_rpc"] is False


def test_model_loaded_without_rpc_consumer_is_not_ready() -> None:
    response = readiness_client(
        model_loaded=True,
        rpc_connected=False,
        kafka_connected=True,
    ).get("/ready")

    assert response.status_code == 503
    assert response.json()["rabbitmq"] == "disconnected"


def test_model_and_rpc_ready_even_when_kafka_is_disconnected() -> None:
    response = readiness_client(
        model_loaded=True,
        rpc_connected=True,
        kafka_connected=False,
    ).get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "embedding",
        "model_loaded": True,
        "rabbitmq": "connected",
        "kafka": "disconnected",
        "ready_for_rpc": True,
    }
    assert "secret" not in response.text.lower()


def test_dependency_failure_and_recovery_do_not_change_liveness() -> None:
    rpc = ConnectionState(True)
    app = FastAPI()
    app.include_router(create_health_router(
        get_producer=lambda: ConnectionState(False),
        get_model=lambda: ModelState(True),
        get_rpc_consumer=lambda: rpc,
    ))
    client = TestClient(app)

    assert client.get("/ready").status_code == 200
    rpc.connected = False
    assert client.get("/ready").status_code == 503
    assert client.get("/live").status_code == 200
    assert client.get("/live").json()["status"] == "live"
    rpc.connected = True
    assert client.get("/ready").status_code == 200
