"""Liveness and readiness endpoints for the vector_db service."""
from typing import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings


def create_health_router(
    qdrant_ready: Callable[[], bool],
    rabbitmq_ready: Callable[[], bool],
    kafka_ready: Callable[[], bool],
) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    @router.get("/live")
    async def live() -> dict:
        return {"status": "live", "service": settings.service_name}

    @router.get("/ready")
    async def ready() -> JSONResponse:
        checks = {
            "qdrant": _safe_check(qdrant_ready),
            "rabbitmq": _safe_check(rabbitmq_ready),
            "kafka": _safe_check(kafka_ready),
        }
        is_ready = all(checks.values())
        return JSONResponse(
            {
                "status": "ready" if is_ready else "not_ready",
                "service": settings.service_name,
                "checks": checks,
            },
            status_code=200 if is_ready else 503,
        )

    return router


def _safe_check(check: Callable[[], bool]) -> bool:
    try:
        return bool(check())
    except Exception:
        return False


def _qdrant_ready() -> bool:
    from app.main import _vector_store

    return bool(_vector_store and _vector_store.count() >= 0)


def _rabbitmq_ready() -> bool:
    from app.main import _rpc_consumer

    return bool(_rpc_consumer and _rpc_consumer.is_connected())


def _kafka_ready() -> bool:
    from app.main import _kafka_consumer_pool

    return bool(_kafka_consumer_pool and _kafka_consumer_pool.is_connected())


router = create_health_router(_qdrant_ready, _rabbitmq_ready, _kafka_ready)
