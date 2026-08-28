"""Health check endpoints."""
from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.constants import SERVICE_PORTS
from app.core.auth import require_admin

router = APIRouter(tags=["health"])

HEALTH_PATHS = {
    "gateway": ("/live", "/ready"),
    "llm_agent": ("/api/v1/live", "/api/v1/ready"),
    "embedding": ("/live", "/ready"),
    "rag": ("/live", "/ready"),
    "files": ("/v1/live", "/v1/ready"),
    "vector_db": ("/api/v1/live", "/api/v1/ready"),
    "memory": ("/live", "/ready"),
}


@router.get("/health")
@router.get("/live")
async def live():
    """Report process liveness without probing downstream services."""
    return {"status": "live", "service": "gateway"}


@router.get("/ready")
async def ready() -> JSONResponse:
    """Require the state store, RPC transport, and serving backends."""
    from app.db.session import get_client
    from app.main import _rpc_client

    def ping_mongodb() -> bool:
        try:
            return bool(get_client().admin.command("ping").get("ok"))
        except Exception:
            return False

    mongodb_ready, downstream = await asyncio.gather(
        asyncio.to_thread(ping_mongodb),
        _critical_services_ready(),
    )
    try:
        rabbitmq_ready = bool(_rpc_client and _rpc_client.is_connected())
    except Exception:
        rabbitmq_ready = False
    is_ready = mongodb_ready and rabbitmq_ready and all(downstream.values())
    return JSONResponse(
        {
            "status": "ready" if is_ready else "not_ready",
            "service": "gateway",
            "checks": {
                "mongodb": mongodb_ready,
                "rabbitmq": rabbitmq_ready,
                **downstream,
            },
        },
        status_code=200 if is_ready else 503,
    )


async def _critical_services_ready() -> dict[str, bool]:
    """Return readiness for the services directly exposed through Gateway."""
    names = ("llm_agent", "memory", "files", "rag")
    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
        results = await asyncio.gather(*(
            _probe_service(client, name, SERVICE_PORTS[name]) for name in names
        ))
    return {f"{result['name']}_ready": bool(result["ready"]) for result in results}


@router.get("/v1/health/detailed", dependencies=[Depends(require_admin)])
async def health_detailed():
    """Detailed health including circuit-breaker and topology state."""
    from app.main import _rabbitmq_client, app  # deferred to avoid circular import

    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
        results = await asyncio.gather(*(
            _probe_service(client, name, port)
            for name, port in SERVICE_PORTS.items()
            if name in HEALTH_PATHS
        ))
    services = {result["name"]: result for result in results}

    circuit_breakers: dict = {}
    if _rabbitmq_client and _rabbitmq_client.circuit_breaker_registry:
        circuit_breakers = _rabbitmq_client.circuit_breaker_registry.get_all_metrics()
        for svc, metrics in circuit_breakers.items():
            if svc not in services:
                continue
            state = metrics.get("state", "unknown")
            if services[svc]["status"] == "healthy" and state in {"open", "half_open"}:
                services[svc]["status"] = "degraded"
                services[svc]["message"] = f"Ready, but circuit breaker is {state}"

    rate_limiter: dict = {}
    try:
        if hasattr(app, "_rate_limiter"):
            rate_limiter = app._rate_limiter.metrics
    except Exception:
        pass

    statuses = [s["status"] for s in services.values()]
    if statuses and all(s == "healthy" for s in statuses):
        overall = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        overall = "unhealthy"
    elif any(s == "degraded" for s in statuses):
        overall = "degraded"
    else:
        overall = "unknown"

    return {
        "status": overall,
        "timestamp": time.time(),
        "services": services,
        "circuit_breakers": circuit_breakers,
        "rate_limiter": rate_limiter,
        "gateway_topology": getattr(app.state, "matcher_topology", {}),
    }


async def _probe_service(
    client: httpx.AsyncClient,
    name: str,
    port: int,
) -> dict:
    """Probe liveness and readiness independently for the admin health UI."""
    live_path, ready_path = HEALTH_PATHS[name]
    host = "127.0.0.1" if name == "gateway" else name
    base_url = f"http://{host}:{port}"

    async def probe(path: str) -> bool:
        try:
            response = await client.get(f"{base_url}{path}")
            return response.status_code == 200
        except (httpx.HTTPError, TimeoutError):
            return False

    live, ready = await asyncio.gather(probe(live_path), probe(ready_path))
    if ready:
        status = "healthy"
        message = "Live and ready for traffic"
    elif live:
        status = "degraded"
        message = "Live but not ready for traffic"
    else:
        status = "unhealthy"
        message = "Liveness probe failed"
    return {
        "name": name,
        "status": status,
        "port": port,
        "live": live,
        "ready": ready,
        "message": message,
    }
