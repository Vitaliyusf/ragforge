"""Tests for structured logging context."""
import json
import uuid

from shared.logging import ServiceLogger
from app.core.request_context import clear_request_context, set_request_context


def _first_json_log_line(log_path):
    """Return the first JSON log line from a mixed log file."""
    with open(log_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line.startswith("{"):
                continue
            return json.loads(line)
    raise AssertionError("No JSON log line found")


def test_logger_includes_request_context():
    """Structured logs should include bound request context."""
    logger = ServiceLogger(service_name=f"gateway-test-{uuid.uuid4()}", log_dir="logs")
    tokens = set_request_context(
        request_id="request-1",
        trace_id="trace-1",
        route="/v1/files/abc/review-case",
        method="GET",
    )
    try:
        logger.log("unit:test", "Structured log", {"status_code": 201, "foo": "bar"})
    finally:
        clear_request_context(tokens)

    entry = _first_json_log_line(logger.log_path)
    assert entry["request_id"] == "request-1"
    assert entry["trace_id"] == "trace-1"
    assert entry["data"]["route"] == "/v1/files/abc/review-case"
    assert entry["data"]["method"] == "GET"
    assert entry["status_code"] == 201
    assert entry["data"]["foo"] == "bar"


def test_access_log_helper_writes_latency():
    """Access helper should emit the expected structured fields."""
    logger = ServiceLogger(service_name=f"gateway-access-{uuid.uuid4()}", log_dir="logs")
    logger.access(
        route="/v1/rag/traces/trace-123",
        method="GET",
        status_code=200,
        latency_ms=12.34,
        request_id="request-2",
        trace_id="trace-2",
    )

    entry = _first_json_log_line(logger.log_path)
    assert entry["location"] == "http:access"
    assert entry["status_code"] == 200
    assert entry["latency_ms"] == 12.34
    assert entry["data"]["request_id"] == "request-2"
    assert entry["data"]["trace_id"] == "trace-2"
