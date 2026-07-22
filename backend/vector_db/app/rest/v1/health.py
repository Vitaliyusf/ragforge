"""Health check endpoint for the vector_db service."""
from fastapi import APIRouter, Depends

from app.core.deps import get_vector_service
from app.services.vector_service import VectorService

router = APIRouter()


@router.get("/health")
async def health(service: VectorService = Depends(get_vector_service)) -> dict:
    """Return a non-sensitive liveness status."""
    kafka_ok = service.producer.is_connected()
    return {
        "status": "ok",
        "kafka": "connected" if kafka_ok else "disconnected",
    }
