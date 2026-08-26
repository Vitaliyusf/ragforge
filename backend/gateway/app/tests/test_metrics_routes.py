"""Tests for the admin metrics routes.

Doubles sit at the service boundary — the RabbitMQ RPC client and the
Prometheus client — and the real ``MetricsService`` runs between them.
Doubling ``MetricsService`` itself would make the "Prometheus is down" test
assert against a stub rather than against the degradation logic that is the
whole point of the route contract.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.core.constants import MetricsWindow
from app.core.deps import get_metrics_service
from app.rest.v1 import metrics as metrics_routes
from app.services.metrics_service import MetricsService
from app.services import promql
from app.services.prometheus_client import PrometheusUnavailable
from shared.auth import AuthIdentity

ROUTES = ["overview", "latency", "retrieval", "quality", "pipeline"]

ENVELOPE_KEYS = {
    "window",
    "tenant_id",
    "generated_at",
    "prometheus_available",
    "prometheus_scope",
    "data",
}

TENANT = "tenant-a"


class DummyRPCClient:
    """Return canned rag and files metric replies, recording every call."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def send_request(self, routing_key, payload, timeout=None):
        self.calls.append({"routing_key": routing_key, "payload": payload})
        if routing_key == "files":
            return {
                "tenant_id": TENANT,
                "funnel": {"files": 4, "by_status": [{"status": "complete", "count": 3}]},
                "task_durations": {"tasks": 3, "p95_seconds": 12.5},
                "stuck_files": {"count": 1, "threshold_minutes": 30, "files": []},
            }
        return {
            "tenant_id": TENANT,
            "overview": {
                "turns": 12,
                "mean_groundedness": 0.81,
                "retrieval_hit_rate": 0.75,
                "thumbs_up_rate": 0.9,
                "tokens_in": 5000,
                "tokens_out": 900,
            },
            "quality": {
                "turns": 12,
                "mean_groundedness": 0.81,
                "hallucination_rate_proxy_groundedness": 0.25,
                "hallucination_groundedness_threshold": 0.6,
            },
            "retrieval": {"turns": 12, "hit_rate": 0.75, "empty_retrieval_rate": 0.25},
            "cost": {
                "by_model": [
                    {"model": "hosted-model", "turns": 12, "tokens_in": 5000, "tokens_out": 900}
                ],
                "tokens_in": 5000,
                "tokens_out": 900,
            },
            "worst_turns": [{"turn_id": "t-1", "groundedness": 0.1}],
        }


class DummyPrometheus:
    """Answer every query with one sample, or fail like a dead container."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.queries: List[str] = []

    async def query(self, expr: str):
        self.queries.append(expr)
        if not self.available:
            raise PrometheusUnavailable("Prometheus request failed")
        return [{"metric": {"answer_mode": "quick", "service": "rag"}, "value": [1, "0.5"]}]

    async def query_range(self, expr, start, end, step):
        self.queries.append(expr)
        if not self.available:
            raise PrometheusUnavailable("Prometheus request failed")
        return [{"metric": {}, "values": [[1, "0.5"], [2, "0.6"]]}]

    async def is_available(self) -> bool:
        return self.available


class DummyLogger:
    """Swallow log calls made by the service under test."""

    def log(self, *args, **kwargs) -> None:
        return None


def build_service(*, prometheus_available: bool = True) -> MetricsService:
    """Wire the real MetricsService onto doubles."""
    config = SimpleNamespace(
        request_topics={"rag": "rag", "files": "files"},
        short_timeout=5.0,
        default_timeout=30.0,
    )
    # The doubles are structural stand-ins, not subclasses, so the constructor's
    # nominal types have to be cast away. The service under test is still real.
    return MetricsService(
        cast(Any, DummyRPCClient()),
        cast(Any, DummyLogger()),
        cast(Any, config),
        cast(Any, DummyPrometheus(available=prometheus_available)),
    )


def rpc_calls(service: MetricsService) -> List[Any]:
    """Calls recorded by the RPC double behind the service."""
    return cast(List[Any], cast(Any, service.rpc_client).calls)


def prom_queries(service: MetricsService) -> List[Any]:
    """Queries recorded by the Prometheus double behind the service."""
    return cast(List[Any], cast(Any, service.prometheus).queries)


def build_app(service, *, role: str = "admin") -> FastAPI:
    """Create a small app around the metrics router."""
    app = FastAPI()
    app.include_router(metrics_routes.router, prefix="/v1")
    app.dependency_overrides[get_metrics_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: AuthIdentity(
        tenant_id=TENANT,
        user_id="admin-a" if role == "admin" else "user-a",
        role=role,
        admin_id="admin-a",
    )
    return app


# ── Happy path ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("route", ROUTES)
def test_every_route_returns_the_shared_envelope(route):
    """All five routes answer with the same top-level contract."""
    service = build_service()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.get(f"/v1/metrics/{route}?window=24h")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == ENVELOPE_KEYS
    assert body["window"] == "24h"
    assert body["prometheus_available"] is True
    assert isinstance(body["data"], dict)


def test_overview_merges_mongo_and_prometheus_fields():
    """The KPI header carries both tenant-scoped and platform-wide numbers."""
    service = build_service()
    app = build_app(service)

    with TestClient(app) as client:
        body = client.get("/v1/metrics/overview?window=24h").json()

    data = body["data"]
    assert data["mean_groundedness"] == 0.81
    assert data["thumbs_up_rate"] == 0.9
    assert data["turn_latency_seconds"]["p95"] == {"quick": 0.5}
    assert data["qps"] == 0.5


def test_prometheus_data_is_labelled_platform_wide():
    """The series carry no tenant label, so the response must say so."""
    service = build_service()
    app = build_app(service)

    with TestClient(app) as client:
        body = client.get("/v1/metrics/overview").json()

    assert body["prometheus_scope"] == "all_tenants"


def test_operational_promql_excludes_eval_traffic():
    """The admin dashboard must show live operational load by default."""
    for name in (
        "rpc_roundtrip_p95",
        "vector_search_p95",
        "vector_search_rate",
        "embedding_p95",
        "llm_p95",
        "llm_token_rate",
    ):
        assert 'traffic_class="live"' in promql.render(name, MetricsWindow.HOUR)


def test_tenant_id_is_echoed_from_the_downstream_service():
    """The envelope names the tenant actually aggregated, not the one asked for."""
    service = build_service()
    app = build_app(service)

    with TestClient(app) as client:
        body = client.get("/v1/metrics/overview?tenant_id=someone-else").json()

    assert body["tenant_id"] == TENANT


def test_quality_route_carries_the_proxy_hallucination_name():
    """The coarse metric must never be surfaced as a bare hallucination rate."""
    service = build_service()
    app = build_app(service)

    with TestClient(app) as client:
        data = client.get("/v1/metrics/quality").json()["data"]

    assert data["hallucination_rate_proxy_groundedness"] == 0.25
    assert data["hallucination_groundedness_threshold"] == 0.6
    assert "hallucination_rate" not in data
    assert data["worst_turns"] == [{"turn_id": "t-1", "groundedness": 0.1}]


def test_pipeline_route_prices_tokens_and_names_unpriced_models():
    """A zero cost must be distinguishable from an unpriced model."""
    service = build_service()
    app = build_app(service)

    with TestClient(app) as client:
        data = client.get("/v1/metrics/pipeline").json()["data"]

    assert data["cost"]["models_without_pricing"] == ["hosted-model"]
    assert data["cost"]["estimated_cost_usd"] == 0.0
    assert data["ingestion"]["funnel"]["files"] == 4


# ── Prometheus down ───────────────────────────────────────────────────────

@pytest.mark.parametrize("route", ROUTES)
def test_dead_prometheus_degrades_instead_of_failing(route):
    """A dead metrics container must never turn a metrics route into a 5xx."""
    service = build_service(prometheus_available=False)
    app = build_app(service)

    with TestClient(app) as client:
        response = client.get(f"/v1/metrics/{route}?window=24h")

    assert response.status_code == 200
    assert response.json()["prometheus_available"] is False


def test_mongo_backed_fields_survive_a_prometheus_outage():
    """The tenant-scoped half of the tab keeps working without Prometheus."""
    service = build_service(prometheus_available=False)
    app = build_app(service)

    with TestClient(app) as client:
        body = client.get("/v1/metrics/overview?window=24h").json()

    data = body["data"]
    assert body["prometheus_available"] is False
    assert data["turns"] == 12
    assert data["mean_groundedness"] == 0.81
    assert data["retrieval_hit_rate"] == 0.75
    # The Prometheus-backed fields are absent rather than zero: an outage
    # means "unknown", and a zeroed p95 would read as a healthy system.
    assert data["turn_latency_seconds"]["p95"] == {}
    assert data["qps"] is None


# ── Authorization and validation ──────────────────────────────────────────

@pytest.mark.parametrize("route", ROUTES)
def test_regular_users_are_forbidden(route):
    """Operational metrics span every user in the tenant, so they are admin-only."""
    service = build_service()
    app = build_app(service, role="user")

    with TestClient(app) as client:
        response = client.get(f"/v1/metrics/{route}")

    assert response.status_code == 403
    assert rpc_calls(service) == []


@pytest.mark.parametrize("window", ["5m", "1y", "24h; drop", "", "rate(x[1h])"])
def test_invalid_window_is_rejected_before_any_query(window):
    """No caller-supplied string may reach a PromQL expression."""
    service = build_service()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.get(f"/v1/metrics/overview?window={window}")

    assert response.status_code == 422
    assert rpc_calls(service) == []
    assert prom_queries(service) == []


@pytest.mark.parametrize("window", ["1h", "24h", "7d", "30d"])
def test_every_allowed_window_is_accepted(window):
    """The allow-list is exactly the four documented windows."""
    service = build_service()
    app = build_app(service)

    with TestClient(app) as client:
        response = client.get(f"/v1/metrics/overview?window={window}")

    assert response.status_code == 200
    assert response.json()["window"] == window


def test_window_is_forwarded_to_the_downstream_service():
    """The rag service validates the window again, so it must receive it."""
    service = build_service()
    app = build_app(service)

    with TestClient(app) as client:
        client.get("/v1/metrics/quality?window=7d")

    assert rpc_calls(service)[0]["payload"]["window"] == "7d"
    assert rpc_calls(service)[0]["payload"]["action"] == "get_metrics"
