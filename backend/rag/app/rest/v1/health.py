"""Liveness and readiness endpoints for the RAG service."""
import asyncio

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
@router.get("/live")
async def live() -> dict:
    """Return process liveness without checking serving dependencies."""
    from app.main import config

    return {
        "status": "live",
        "service": config.service_name,
        "store": config.conversation_store_type,
    }


@router.get("/ready")
async def ready() -> JSONResponse:
    """Require persistence, RabbitMQ, and the primary RAG serving chain."""
    from app.main import conversation_store, fastapi_app, rpc_client

    def check_store() -> bool:
        try:
            return bool(conversation_store.is_available())
        except Exception:
            return False

    store_ready, downstream = await asyncio.gather(
        asyncio.to_thread(check_store),
        _critical_services_ready(),
    )
    try:
        rpc_ready = bool(rpc_client.is_connected())
    except Exception:
        rpc_ready = False
    consumer = getattr(fastapi_app.state, "rpc_consumer", None)
    try:
        consumer_ready = bool(consumer and consumer.is_connected())
    except Exception:
        consumer_ready = False
    is_ready = store_ready and rpc_ready and consumer_ready and all(downstream.values())
    return JSONResponse(
        {
            "status": "ready" if is_ready else "not_ready",
            "service": "rag",
            "checks": {
                "conversation_store": store_ready,
                "rabbitmq_rpc": rpc_ready,
                "rabbitmq_consumer": consumer_ready,
                **downstream,
            },
        },
        status_code=200 if is_ready else 503,
    )


async def _critical_services_ready() -> dict[str, bool]:
    """Probe the primary retrieval/generation chain concurrently."""
    endpoints = {
        "embedding_ready": "http://embedding:8002/ready",
        "vector_db_ready": "http://vector_db:8006/api/v1/ready",
        "llm_agent_ready": "http://llm_agent:8001/api/v1/ready",
        "memory_ready": "http://memory:8007/ready",
    }

    async def probe(client: httpx.AsyncClient, name: str, url: str) -> tuple[str, bool]:
        try:
            response = await client.get(url)
            return name, response.status_code == 200
        except (httpx.HTTPError, TimeoutError):
            return name, False

    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
        results = await asyncio.gather(*(
            probe(client, name, url) for name, url in endpoints.items()
        ))
    return dict(results)
