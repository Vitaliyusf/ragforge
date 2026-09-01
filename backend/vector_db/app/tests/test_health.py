"""Truthful health contract tests for vector_db."""
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.rest.v1.health import _kafka_ready, create_health_router


def test_qdrant_failure_live_and_recovery() -> None:
    state = {"qdrant": True, "rabbitmq": True, "kafka": True}
    app = FastAPI()
    app.include_router(create_health_router(
        lambda: state["qdrant"],
        lambda: state["rabbitmq"],
        lambda: state["kafka"],
    ))
    client = TestClient(app)

    assert client.get("/ready").status_code == 200
    state["qdrant"] = False
    assert client.get("/ready").status_code == 503
    assert client.get("/live").status_code == 200
    state["qdrant"] = True
    assert client.get("/ready").status_code == 200


def test_probe_exception_is_not_ready() -> None:
    def fail() -> bool:
        raise TimeoutError

    app = FastAPI()
    app.include_router(create_health_router(fail, lambda: True, lambda: True))
    assert TestClient(app).get("/ready").status_code == 503


def test_kafka_probe_uses_worker_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = SimpleNamespace(is_connected=lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "app.main",
        SimpleNamespace(_kafka_consumer_pool=pool),
    )

    assert _kafka_ready() is True
