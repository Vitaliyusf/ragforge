"""Health check endpoints."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from app.core.constants import SERVICE_PORTS
from app.core.auth import require_admin

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Simple liveness probe."""
    return {"status": "ok"}


@router.get("/v1/health/detailed", dependencies=[Depends(require_admin)])
async def health_detailed():
    """Detailed health including circuit-breaker and topology state."""
    from app.main import _rabbitmq_client, _HAS_RATE_LIMITER, app  # deferred to avoid circular import

    services = {
        name: {"status": "healthy" if name == "gateway" else "unknown", "port": port}
        for name, port in SERVICE_PORTS.items()
    }

    circuit_breakers: dict = {}
    if _rabbitmq_client and _rabbitmq_client.circuit_breaker_registry:
        circuit_breakers = _rabbitmq_client.circuit_breaker_registry.get_all_metrics()
        for svc, metrics in circuit_breakers.items():
            if svc not in services:
                continue
            state = metrics.get("state", "unknown")
            services[svc]["status"] = {"closed": "healthy", "open": "degraded", "half_open": "partial"}.get(state, "unknown")

    rate_limiter: dict = {}
    try:
        if _HAS_RATE_LIMITER and hasattr(app, "_rate_limiter"):
            rate_limiter = app._rate_limiter.metrics
    except Exception:
        pass

    statuses = [s["status"] for s in services.values()]
    if all(s == "healthy" for s in statuses):
        overall = "healthy"
    elif any(s == "degraded" for s in statuses):
        overall = "degraded"
    else:
        overall = "partial"

    return {
        "status": overall,
        "timestamp": time.time(),
        "services": services,
        "circuit_breakers": circuit_breakers,
        "rate_limiter": rate_limiter,
        "gateway_topology": getattr(app.state, "matcher_topology", {}),
    }
