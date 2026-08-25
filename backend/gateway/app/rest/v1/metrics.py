"""Admin metrics API routes.

Every route is admin-only, accepts ``?window=`` from a fixed allow-list and
an optional ``&tenant_id=``, and returns the shared metrics envelope:

    {"window", "tenant_id", "generated_at", "prometheus_available",
     "prometheus_scope", "data"}

``window`` is typed as :class:`MetricsWindow`, so FastAPI rejects anything
outside the allow-list with a 422 before the value could reach a PromQL
expression or a MongoDB pipeline.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from app.core.auth import require_admin
from app.core.constants import MetricsWindow
from app.core.deps import get_metrics_service
from app.core.errors import handle_exception
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])

_WINDOW = Query(MetricsWindow.DAY, description="Lookback window")
_TENANT = Query(None, description="Tenant to report on; defaults to your own")


@router.get("/overview", dependencies=[Depends(require_admin)])
async def metrics_overview(
    window: MetricsWindow = _WINDOW,
    tenant_id: Optional[str] = _TENANT,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """KPI header: turn latency, TTFT, QPS, errors, quality, tokens, cost."""
    try:
        return await service.overview(window, tenant_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/latency", dependencies=[Depends(require_admin)])
async def metrics_latency(
    window: MetricsWindow = _WINDOW,
    tenant_id: Optional[str] = _TENANT,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Latency time series, stage breakdown, HTTP percentiles, RPC timings."""
    try:
        return await service.latency(window, tenant_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/retrieval", dependencies=[Depends(require_admin)])
async def metrics_retrieval(
    window: MetricsWindow = _WINDOW,
    tenant_id: Optional[str] = _TENANT,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Hit rate, score histogram, chunks per query, reranker lift, search p95."""
    try:
        return await service.retrieval(window, tenant_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/quality", dependencies=[Depends(require_admin)])
async def metrics_quality(
    window: MetricsWindow = _WINDOW,
    tenant_id: Optional[str] = _TENANT,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Score distributions, confidence mix, proxy hallucination, worst turns."""
    try:
        return await service.quality(window, tenant_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/pipeline", dependencies=[Depends(require_admin)])
async def metrics_pipeline(
    window: MetricsWindow = _WINDOW,
    tenant_id: Optional[str] = _TENANT,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Ingestion funnel, stage durations, stuck files, throughput, token cost."""
    try:
        return await service.pipeline(window, tenant_id)
    except Exception as exc:
        raise handle_exception(exc)
