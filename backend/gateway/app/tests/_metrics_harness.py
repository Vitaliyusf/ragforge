"""Shared doubles and app builders for the admin metrics router tests.

Doubles sit at the service boundary — the RabbitMQ RPC client and the
Prometheus client — and the real ``MetricsService`` runs between them.
Doubling ``MetricsService`` itself would make the "Prometheus is down" test
assert against a stub rather than against the degradation logic that is the
whole point of the route contract.

Each lane brings its own ``DummyRPCClient``: the canned replies are what those
tests are about, and merging them would make every assertion read through one
oversized reply table.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, cast

from fastapi import FastAPI

from app.core.auth import get_current_user
from app.core.deps import get_metrics_service
from app.rest.v1 import metrics as metrics_routes
from app.services.metrics_service import MetricsService
from app.services.prometheus_client import PrometheusUnavailable
from shared.auth import AuthIdentity

TENANT = "tenant-a"


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


def build_service(rpc_client, *, prometheus_available: bool = True) -> MetricsService:
    """Wire the real MetricsService onto the supplied RPC double."""
    config = SimpleNamespace(
        request_topics={"rag": "rag", "files": "files"},
        short_timeout=5.0,
        default_timeout=30.0,
    )
    # The doubles are structural stand-ins, not subclasses, so the constructor's
    # nominal types have to be cast away. The service under test is still real.
    return MetricsService(
        cast(Any, rpc_client),
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


def last_payload(service: MetricsService) -> Dict[str, Any]:
    """Payload of the most recent RPC the routes sent."""
    return cast(Dict[str, Any], rpc_calls(service)[-1]["payload"])


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
