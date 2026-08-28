"""Health check endpoints."""
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.deps import get_consumers, get_llm_client
from app.llm.interfaces import ILLMClient

router = APIRouter()


@router.get("/health")
@router.get("/live")
async def live() -> Dict[str, Any]:
    """Return process liveness without invoking downstream dependencies."""
    settings = get_settings()
    return {
        "status": "live",
        "service": settings.service_name,
        "llm_implementation": settings.llm_implementation,
        "timestamp": int(time.time()),
    }


@router.get("/ready")
async def ready(
    llm_client: Optional[ILLMClient] = Depends(get_llm_client),
    consumers: List = Depends(get_consumers),
) -> JSONResponse:
    """Require the model backend and every serving queue consumer."""
    settings = get_settings()
    try:
        llm_ready = bool(llm_client and llm_client.is_available())
    except Exception:
        llm_ready = False
    try:
        connected = sum(1 for consumer in consumers if consumer.is_connected())
        rabbitmq_ready = bool(consumers) and connected == len(consumers)
    except Exception:
        rabbitmq_ready = False
    is_ready = llm_ready and rabbitmq_ready
    return JSONResponse(
        {
            "status": "ready" if is_ready else "not_ready",
            "service": settings.service_name,
            "checks": {
                "rabbitmq": rabbitmq_ready,
                "llm_backend": llm_ready,
            },
        },
        status_code=200 if is_ready else 503,
    )
