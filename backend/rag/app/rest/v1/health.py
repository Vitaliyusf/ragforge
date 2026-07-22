"""Health endpoint for the rag service."""
from fastapi import APIRouter

from app.core.config import RAGConfig

router = APIRouter()


@router.get("/health")
async def health(config: RAGConfig = None) -> dict:
    """Return a lightweight runtime health summary for the active service path."""
    from app.main import config as _config  # deferred — avoids circular import at module load

    return {
        "status": "ok",
        "service": _config.service_name,
        "store": _config.conversation_store_type,
    }
