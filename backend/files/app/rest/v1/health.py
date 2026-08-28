"""Liveness and readiness endpoints for the files service."""
import time
from typing import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings


def create_health_router(
    mongodb_ready: Callable[[], bool],
    rabbitmq_ready: Callable[[], bool],
    kafka_ready: Callable[[], bool],
) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    @router.get("/live")
    async def live() -> dict:
        return {
            "status": "live",
            "service": settings.service_name,
            "timestamp": int(time.time()),
        }

    @router.get("/ready")
    async def ready() -> JSONResponse:
        checks = {
            "mongodb": _safe_check(mongodb_ready),
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


def _mongodb_ready() -> bool:
    from app.db.session import get_client

    return bool(get_client().admin.command("ping").get("ok"))


def _rabbitmq_ready() -> bool:
    from app.main import _consumer

    return bool(_consumer and _consumer.is_connected())


def _kafka_ready() -> bool:
    from app.main import _kafka_consumer

    return bool(_kafka_consumer and _kafka_consumer.is_connected())


router = create_health_router(_mongodb_ready, _rabbitmq_ready, _kafka_ready)
