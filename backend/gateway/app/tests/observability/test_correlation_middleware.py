"""Tests for correlation middleware and response headers."""
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.http_middleware import CorrelationMiddleware
from app.core.exception_handlers import http_exception_handler, validation_exception_handler


class CaptureLogger:
    """Small logger stub that records access log entries."""

    def __init__(self) -> None:
        self.access_logs: list = []

    def access(self, **kwargs) -> None:
        self.access_logs.append(kwargs)


def build_app():
    """Create a small app with the correlation middleware installed."""
    app = FastAPI()
    app.state.service_logger = CaptureLogger()
    app.add_middleware(CorrelationMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/fail")
    async def fail():
        raise HTTPException(status_code=404, detail="missing")

    return app


def test_middleware_generates_and_logs_ids():
    """Missing correlation headers should be generated and logged."""
    app = build_app()

    with TestClient(app) as client:
        response = client.get("/ok")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Trace-ID"]
    access_log = app.state.service_logger.access_logs[0]
    assert access_log["route"] == "/ok"
    assert access_log["method"] == "GET"
    assert access_log["status_code"] == 200
    assert access_log["request_id"] == response.headers["X-Request-ID"]
    assert access_log["trace_id"] == response.headers["X-Trace-ID"]


def test_middleware_preserves_incoming_ids():
    """Provided correlation headers should flow through unchanged."""
    app = build_app()

    with TestClient(app) as client:
        response = client.get(
            "/ok",
            headers={
                "X-Request-ID": "request-123",
                "X-Trace-ID": "trace-456",
            },
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-123"
    assert response.headers["X-Trace-ID"] == "trace-456"


def test_middleware_adds_headers_on_error_path():
    """Handled errors should still carry correlation headers and metadata."""
    app = build_app()

    with TestClient(app) as client:
        response = client.get("/fail")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "not_found"
    assert body["message"] == "missing"
    assert body["code"] == "NOT_FOUND"
    assert body["origin"]["service"] == "gateway"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["trace_id"] == response.headers["X-Trace-ID"]
