"""Health check route for the embedding service."""
from typing import Callable

from fastapi import APIRouter


def create_health_router(
    get_producer: Callable,
    get_model: Callable,
) -> APIRouter:
    """Return a health router that reads singletons via getter functions.

    Args:
        get_producer: Callable returning the live IProducer singleton (or None).
        get_model: Callable returning the live IEmbeddingModel singleton (or None).
    """
    router = APIRouter()

    @router.get("/health")
    async def health():
        """Report service-local health state."""
        producer = get_producer()
        model = get_model()
        return {
            "status": "ok",
            "model_loaded": model.is_loaded() if model else False,
            "kafka": "connected" if (producer and producer.is_connected()) else "disconnected",
        }

    return router
