"""Health check endpoints."""
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.deps import get_consumers, get_llm_client
from app.llm.interfaces import ILLMClient

router = APIRouter()


@router.get("/health")
async def health_check(
    llm_client: Optional[ILLMClient] = Depends(get_llm_client),
    consumers: List = Depends(get_consumers),
) -> Dict[str, Any]:
    """Return full runtime health for the llm_agent service.

    Checks:
    - ``rabbitmq_consumers``: how many RabbitMQ consumers are active.
    - ``llm_client``:         whether the active LLM backend reports as available.
    """
    settings = get_settings()
    connected = [c for c in consumers if c.is_connected()]
    return {
        "status": "ok",
        "service": settings.service_name,
        "llm_implementation": settings.llm_implementation,
        "timestamp": int(time.time()),
        "checks": {
            "rabbitmq_consumers": f"{len(connected)}/{len(consumers)} connected",
            "llm_client": "ok" if (llm_client and llm_client.is_available()) else "unavailable",
        },
    }
