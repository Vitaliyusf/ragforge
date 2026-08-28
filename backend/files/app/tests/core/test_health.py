"""Truthful health contract tests for the files service."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rest.v1.health import create_health_router


def test_ready_failure_live_and_recovery() -> None:
    state = {"mongodb": True, "rabbitmq": True, "kafka": True}
    app = FastAPI()
    app.include_router(create_health_router(
        lambda: state["mongodb"],
        lambda: state["rabbitmq"],
        lambda: state["kafka"],
    ))
    client = TestClient(app)

    assert client.get("/ready").status_code == 200
    state["mongodb"] = False
    failed = client.get("/ready")
    assert failed.status_code == 503
    assert failed.json()["status"] == "not_ready"
    assert client.get("/live").status_code == 200
    state["mongodb"] = True
    assert client.get("/ready").status_code == 200


def test_uninitialized_or_erroring_dependency_is_not_ready() -> None:
    def timeout() -> bool:
        raise TimeoutError("probe timed out")

    app = FastAPI()
    app.include_router(create_health_router(timeout, lambda: False, lambda: False))
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {
        "mongodb": False,
        "rabbitmq": False,
        "kafka": False,
    }
