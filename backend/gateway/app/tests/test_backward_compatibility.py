"""Tests for backward-compatible HTTP behavior."""
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.http_middleware import CorrelationMiddleware
from app.core.exception_handlers import http_exception_handler, validation_exception_handler


class CaptureLogger:
    """Logger stub used by compatibility tests."""

    def access(self, **kwargs) -> None:
        return None


def build_app():
    """Create a lightweight app using the gateway exception handlers."""
    app = FastAPI()
    app.state.service_logger = CaptureLogger()
    app.add_middleware(CorrelationMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

    @app.get("/legacy")
    async def legacy():
        return {"response": "ok"}

    @app.get("/error")
    async def error():
        raise HTTPException(status_code=404, detail="missing")

    return app


def test_existing_success_body_shape_stays_intact():
    """Legacy success bodies should stay unchanged apart from headers."""
    app = build_app()

    with TestClient(app) as client:
        response = client.get(
            "/legacy",
            headers={"X-Request-ID": "request-legacy", "X-Trace-ID": "trace-legacy"},
        )

    assert response.status_code == 200
    assert response.json() == {"response": "ok"}
    assert response.headers["X-Request-ID"] == "request-legacy"
    assert response.headers["X-Trace-ID"] == "trace-legacy"


def test_existing_error_body_shape_is_preserved_with_additive_metadata():
    """Legacy errors should keep error/message while adding correlation metadata."""
    app = build_app()

    with TestClient(app) as client:
        response = client.get("/error")

    body = response.json()
    assert response.status_code == 404
    assert body["error"] == "not_found"
    assert body["message"] == "missing"
    assert body["code"] == "NOT_FOUND"
    assert body["origin"]["service"] == "gateway"
    assert body["origin"]["location"] == "gateway:http_exception_handler"
    assert body["retryable"] is False
    assert body["status_code"] == 404
    assert "detail" not in body
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["trace_id"] == response.headers["X-Trace-ID"]
