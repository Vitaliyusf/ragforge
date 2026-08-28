"""FastAPI application entry point for the llm_agent service."""
import asyncio
from contextvars import copy_context
from contextlib import asynccontextmanager
from typing import List

try:
    from shared.metrics import setup_metrics
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

from fastapi import FastAPI

from app.core.config import get_settings, Settings
from shared.logging import ServiceLogger, setup_logging
from app.messaging.factories import MessageQueueFactory
from app.messaging.handlers import (
    LLMHandler,
    SummaryHandler,
    MetadataHandler,
    GenerateQuestionsHandler,
    ModelHandler,
    ModelManagementHandler,
    ConfigManagementHandler,
)
from app.llm.factories import LLMClientFactory
from app.llm.interfaces import ILLMClient
from app.cache.factories import ModelCacheFactory
from app.cache.interfaces import IModelCache
from app.services.llm_service import LLMService
from app.services.summary_service import SummaryService
from app.services.metadata_service import MetadataService
from app.services.model_service import ModelService
from app.services.config_service import ConfigService
from app.messaging.implementations.rabbitmq import RabbitMQProducerImpl
from app.rest.routes import setup_routes

# ---------------------------------------------------------------------------
# Singletons (initialised at import time; replaced atomically on LLM switch)
# ---------------------------------------------------------------------------

settings: Settings = get_settings()
logger: ServiceLogger = setup_logging(settings.service_name)

llm_client: ILLMClient = LLMClientFactory.create(settings, settings.llm_implementation)
model_cache: IModelCache = ModelCacheFactory.create(settings, settings.models_cache_implementation)

llm_service = LLMService(llm_client, logger, settings)
summary_service = SummaryService(llm_client, logger, settings)
metadata_service = MetadataService(llm_client, logger, settings)
model_service = ModelService(llm_client, model_cache, logger, settings)
config_service = ConfigService(logger, settings)

# Consumer list — populated in lifespan startup
_consumers: List = []


def _startup_llm_checks() -> None:
    """Check LLM availability, cache models, and optionally preload on startup."""
    if not (llm_client and llm_client.is_available()):
        logger.log("main:startup", "LLM service not available", {"implementation": settings.llm_implementation}, hypothesis_id="W")
        return

    logger.log("main:startup", "LLM service connection successful", {"implementation": settings.llm_implementation})
    try:
        models = llm_client.list_models()
        if models:
            model_cache.set_models(models)
            logger.log("main:startup", "Models fetched and cached", {"count": len(models), "models": models})
        else:
            logger.log("main:startup", "LLM service ready, models will be loaded on-demand", {})
    except Exception as e:
        logger.log("main:startup", "Error fetching models on startup", {"error": str(e)}, hypothesis_id="W")

    if settings.preload_models_on_startup and hasattr(llm_client, "preload_models"):
        try:
            model_configs = {"summarization": settings.summary_model, "text-generation": settings.metadata_model}
            if settings.rag_chat_model and settings.rag_chat_model != settings.metadata_model:
                model_configs["text-generation"] = settings.rag_chat_model
            llm_client.preload_models(model_configs)
            logger.log("main:startup", "Model preloading initiated", {"models": model_configs})
        except Exception as e:
            logger.log("main:startup", "Error preloading models", {"error": str(e)}, hypothesis_id="W")


def _rebuild_llm_stack(new_impl: str, producer: RabbitMQProducerImpl) -> None:
    """Recreate all LLM-dependent services and handlers after an implementation switch.

    Called exclusively from the config_management consumer handler.
    """
    global llm_client, llm_service, summary_service, metadata_service, model_service

    llm_client = LLMClientFactory.create(settings, new_impl)
    llm_service = LLMService(llm_client, logger, settings)
    summary_service = SummaryService(llm_client, logger, settings)
    metadata_service = MetadataService(llm_client, logger, settings)
    model_service = ModelService(llm_client, model_cache, logger, settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumers

    logger.log("main:startup", "LLM Agent service starting up", {
        "service_name": settings.service_name,
        "service_port": settings.service_port,
        "llm_implementation": settings.llm_implementation,
        "device": settings.device,
        "primary_prefetch": settings.llm_request_prefetch,
        "max_concurrent_requests": settings.max_concurrent_requests,
        "vllm_max_tokens": settings.vllm_max_tokens,
        "answer_generation_max_tokens": settings.answer_generation_max_tokens,
        "answer_evaluation_max_tokens": settings.answer_evaluation_max_tokens,
        "content_risk_scan_max_tokens": settings.content_risk_scan_max_tokens,
        "query_rewrite_max_tokens": settings.query_rewrite_max_tokens,
        "memory_extraction_max_tokens": settings.memory_extraction_max_tokens,
    })

    _startup_llm_checks()

    producer = MessageQueueFactory.create_producer(settings)
    await producer.connect()

    handlers = [
        (settings.rabbitmq_queue,            LLMHandler(producer, llm_service, logger, settings)),
        (settings.summary_queue,             SummaryHandler(producer, summary_service, logger, settings)),
        (settings.metadata_queue,            MetadataHandler(producer, metadata_service, logger, settings)),
        (settings.generate_questions_queue,  GenerateQuestionsHandler(producer, llm_service, logger, settings)),
        (settings.model_queue,               ModelHandler(producer, model_service, logger, settings)),
        (settings.model_management_queue,    ModelManagementHandler(producer, model_service, logger, settings)),
        (settings.config_management_queue,   ConfigManagementHandler(producer, config_service, logger, settings)),
    ]

    loop = asyncio.get_running_loop()

    for queue_name, handler in handlers:
        consumer = MessageQueueFactory.create_consumer(settings, queue_name)

        # Capture handler in closure to avoid late-binding issues
        def _make_handle(h):
            async def _handle(body, reply_to, correlation_id):
                return await loop.run_in_executor(
                    None,
                    copy_context().run,
                    h.process_request_with_reply,
                    body,
                    reply_to,
                    correlation_id,
                    loop,
                )
            return _handle

        await consumer.start(_make_handle(handler))
        _consumers.append(consumer)

    logger.log("main:startup", "All RabbitMQ consumers started", {
        "queues": [q for q, _ in handlers],
        "llm_request_prefetch": settings.llm_request_prefetch,
        "auxiliary_queue_prefetch": settings.rabbitmq_prefetch_count,
    })

    try:
        yield
    finally:
        logger.log("main:shutdown", "LLM Agent service shutting down gracefully", {})

        for consumer in _consumers:
            try:
                await consumer.stop()
            except Exception:
                pass

        _consumers.clear()

        try:
            await producer.close()
        except Exception:
            pass

        logger.log("main:shutdown", "LLM Agent service shutdown complete", {})


app = FastAPI(title="LLM Agent Service", lifespan=lifespan)
setup_routes(app)
if _HAS_METRICS:
    setup_metrics(app, "llm_agent")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.service_host, port=settings.service_port)
