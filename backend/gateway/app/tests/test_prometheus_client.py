"""Tests for the Prometheus HTTP client.

``httpx.MockTransport`` is used rather than patching methods, so every test
drives the real ``AsyncClient`` and the real parsing code, and only the
socket is fake.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import httpx
import pytest

from app.services.prometheus_client import PrometheusClient, PrometheusUnavailable


def build_client(handler) -> PrometheusClient:
    """Wrap a request handler in a client backed by a mock transport."""
    return PrometheusClient(
        "http://prometheus:9090",
        client=httpx.AsyncClient(
            base_url="http://prometheus:9090",
            transport=httpx.MockTransport(handler),
        ),
    )


def run(coroutine):
    """Drive one coroutine to completion without the asyncio plugin."""
    return asyncio.run(coroutine)


def success(result: List[Dict[str, Any]]) -> httpx.Response:
    """Build a successful Prometheus API envelope."""
    return httpx.Response(
        200,
        json={"status": "success", "data": {"resultType": "matrix", "result": result}},
    )


def test_query_range_parses_the_result_series():
    """A range query should return the raw result entries untouched."""
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        return success(
            [{"metric": {"le": "1"}, "values": [[1700000000, "0.42"], [1700000015, "0.55"]]}]
        )

    client = build_client(handler)
    result = run(client.query_range("up", 1700000000, 1700000015, "15s"))

    assert result[0]["values"] == [[1700000000, "0.42"], [1700000015, "0.55"]]
    assert captured["url"].path == "/api/v1/query_range"


def test_query_range_sends_start_end_and_step():
    """The range bounds must actually reach Prometheus, not just be accepted."""
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return success([])

    client = build_client(handler)
    run(client.query_range("up", 1700000000, 1700003600, "5m"))

    assert captured["params"]["query"] == "up"
    assert captured["params"]["start"] == "1700000000"
    assert captured["params"]["end"] == "1700003600"
    assert captured["params"]["step"] == "5m"


def test_query_returns_empty_list_when_nothing_matched():
    """An empty result is a real answer and must not look like a failure."""
    client = build_client(lambda request: success([]))

    assert run(client.query("up")) == []


def test_transport_error_becomes_prometheus_unavailable():
    """A dead container must not leak a raw httpx exception to callers."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = build_client(handler)

    with pytest.raises(PrometheusUnavailable):
        run(client.query("up"))


def test_timeout_becomes_prometheus_unavailable():
    """A hung Prometheus is an availability problem, not a crash."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = build_client(handler)

    with pytest.raises(PrometheusUnavailable):
        run(client.query_range("up", 0, 1, "5m"))


def test_non_200_status_becomes_prometheus_unavailable():
    """A 503 from Prometheus is as unusable as no response at all."""
    client = build_client(lambda request: httpx.Response(503, text="unavailable"))

    with pytest.raises(PrometheusUnavailable):
        run(client.query("up"))


def test_non_json_body_becomes_prometheus_unavailable():
    """A proxy error page must not be parsed as a result set."""
    client = build_client(lambda request: httpx.Response(200, text="<html>oops</html>"))

    with pytest.raises(PrometheusUnavailable):
        run(client.query("up"))


def test_failed_query_status_becomes_prometheus_unavailable():
    """Prometheus reports a bad expression with status "error", not a 4xx."""
    client = build_client(
        lambda request: httpx.Response(
            200, json={"status": "error", "error": "parse error"}
        )
    )

    with pytest.raises(PrometheusUnavailable):
        run(client.query("not a query"))


def test_is_available_reports_true_when_healthy():
    """The health probe answers the availability question directly."""
    client = build_client(lambda request: httpx.Response(200, text="Healthy"))

    assert run(client.is_available()) is True


def test_is_available_reports_false_instead_of_raising():
    """Asking whether Prometheus is up must never itself raise."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = build_client(handler)

    assert run(client.is_available()) is False
