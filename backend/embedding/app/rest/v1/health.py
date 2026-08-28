"""Health check route for the embedding service."""
from typing import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse


def create_health_router(
    get_producer: Callable,
    get_model: Callable,
    get_rpc_consumer: Callable,
) -> APIRouter:
    """Return a health router that reads singletons via getter functions.

    Args:
        get_producer: Callable returning the live IProducer singleton (or None).
        get_model: Callable returning the live IEmbeddingModel singleton (or None).
        get_rpc_consumer: Callable returning the live RabbitMQ consumer (or None).
    """
    router = APIRouter()

    @router.get("/health")
    @router.get("/live")
    async def live():
        """Report process liveness without gating on downstream services."""
        return {"status": "live", "service": "embedding"}

    @router.get("/ready")
    async def ready():
        """Report whether retrieval RPC traffic can be served safely."""
        producer = get_producer()
        model = get_model()
        rpc_consumer = get_rpc_consumer()
        model_loaded = _safe_state(model, "is_loaded")
        rabbitmq_connected = _safe_state(rpc_consumer, "is_connected")
        ready_for_rpc = model_loaded and rabbitmq_connected
        payload = {
            "status": "ready" if ready_for_rpc else "not_ready",
            "service": "embedding",
            "model_loaded": model_loaded,
            "rabbitmq": "connected" if rabbitmq_connected else "disconnected",
            "kafka": "connected" if _safe_state(producer, "is_connected") else "disconnected",
            "ready_for_rpc": ready_for_rpc,
        }
        return JSONResponse(payload, status_code=200 if ready_for_rpc else 503)

    return router


def _safe_state(dependency, method_name: str) -> bool:
    try:
        return bool(dependency and getattr(dependency, method_name)())
    except Exception:
        return False
