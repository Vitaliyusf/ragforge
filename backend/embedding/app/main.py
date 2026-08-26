"""FastAPI entrypoint for the embedding service.

Exposes GET /health and starts three background Kafka consumer threads:
  - legacy direct embedding requests  (embedding_requests)
  - legacy extraction requests         (extract)
  - typed embedding job requests       (embedding.jobs.requested)
"""
import asyncio
from contextvars import copy_context
from contextlib import asynccontextmanager
from functools import partial
from threading import Thread

from fastapi import FastAPI

try:
    from shared.metrics import setup_metrics
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

from app.config import EmbeddingConfig
from app.core.cors import setup_cors
from app.core.logging_config import ServiceLogger
from app.consumers import (
    process_embedding_job_requests,
    process_embedding_requests,
    process_extraction_requests,
)
from app.embedding.factories import EmbeddingModelFactory
from app.extraction.factories import FileExtractorFactory
from app.messaging.embedding_kafka import EmbeddingKafkaConsumer, EmbeddingKafkaProducer
from app.messaging.threadsafe_rabbitmq import ThreadsafeRabbitMQPublisher
from app.messaging.factories import MessageQueueFactory
from app.rest.v1.health import create_health_router
from app.services.embedding_handler import EmbeddingHandler
from app.services.embedding_job_service import EmbeddingJobService
from app.services.embedding_job_tracing import EmbeddingLangSmithTracer
from app.services.embedding_job_worker import EmbeddingJobConsumerWorker
from app.services.extraction_handler import ExtractionHandler

# ------------------------------------------------------------------
# Module-level singletons — initialised inside lifespan, not at import time
# ------------------------------------------------------------------
_running: bool = False
_config = None
_logger = None
_producer = None
_consumer = None
_extract_consumer = None
_job_consumer = None
_embedding_model = None
_embedding_handler = None
_extraction_handler = None
_job_worker = None
_rpc_consumer = None
_rpc_producer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _running, _config, _logger, _producer, _consumer, _extract_consumer
    global _job_consumer, _embedding_model, _embedding_handler, _extraction_handler, _job_worker
    global _rpc_consumer, _rpc_producer

    # --- startup ---
    _config = EmbeddingConfig()
    _logger = ServiceLogger(_config.service_name)

    _producer = MessageQueueFactory.create_producer(_config)
    _rpc_producer = MessageQueueFactory.create_rabbitmq_producer(_config)
    await _rpc_producer.connect()
    rpc_publisher = ThreadsafeRabbitMQPublisher(
        _rpc_producer,
        asyncio.get_running_loop(),
    )
    _consumer = MessageQueueFactory.create_consumer(_config, _config.request_topic)
    _extract_consumer = MessageQueueFactory.create_consumer(_config, _config.extract_topic)
    _job_consumer = EmbeddingKafkaConsumer(_config)
    job_producer = EmbeddingKafkaProducer(
        producer=_producer,
        upsert_topic=_config.vector_db_upsert_requested_topic,
        completed_topic=_config.embedding_jobs_completed_topic,
    )

    _embedding_model = EmbeddingModelFactory.create(_config)
    if _embedding_model is None:
        _logger.log("main:startup", "No embedding model available", {}, hypothesis_id="W")

    extractors = FileExtractorFactory.create_all()
    if not extractors:
        _logger.log("main:startup", "No file extractors available", {}, hypothesis_id="W")

    job_tracer = EmbeddingLangSmithTracer(
        enabled=_config.langsmith_tracing,
        api_key=_config.langsmith_api_key,
        project=_config.langsmith_project,
    )
    job_service = EmbeddingJobService(
        producer=job_producer,
        embedding_model=_embedding_model,
        logger=_logger,
        config=_config,
        tracer=job_tracer,
    )
    _job_worker = EmbeddingJobConsumerWorker(_job_consumer, job_service, _logger)
    _embedding_handler = EmbeddingHandler(
        _producer, _embedding_model, _logger,
        _config.response_topic, _config.vector_db_topic, _config.files_topic, _config,
    )
    _extraction_handler = ExtractionHandler(
        _producer, extractors, _logger,
        _config.files_topic, "summary", "metadata", _config.request_topic, _config,
        rpc_producer=rpc_publisher,
    )

    _running = True
    _logger.log("main:startup", "Embedding service starting up", {
        "service_name": _config.service_name,
        "port": _config.service_port,
        "model_loaded": _embedding_model.is_loaded() if _embedding_model else False,
        "extractors_count": len(extractors) if extractors else 0,
    })

    flag = lambda: _running  # noqa: E731
    threads = [
        Thread(target=partial(process_embedding_requests, _consumer, _embedding_handler, _logger, _config, flag), daemon=True, name="EmbeddingConsumer"),
        Thread(target=partial(process_embedding_job_requests, _job_consumer, _job_worker, _logger, _config, flag), daemon=True, name="EmbeddingJobConsumer"),
        Thread(target=partial(process_extraction_requests, _extract_consumer, _extraction_handler, _logger, _config, flag), daemon=True, name="ExtractionConsumer"),
    ]
    for t in threads:
        t.start()
    _logger.log("main:startup", "Consumer threads started")

    # RabbitMQ consumer for gateway RPC requests
    _rpc_consumer = MessageQueueFactory.create_rabbitmq_consumer(_config)

    async def _handle_rpc(body, reply_to, correlation_id):
        import asyncio
        body = dict(body)  # shallow copy
        body.setdefault("reply_to", reply_to)
        body.setdefault("correlation_id", correlation_id)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, copy_context().run, _embedding_handler.process_request_with_reply, body, reply_to, correlation_id)

    await _rpc_consumer.start(_handle_rpc)
    _logger.log("main:readiness", "RabbitMQ RPC consumer connected", {
        "queue": _config.rabbitmq_queue,
    })
    if _embedding_model and _embedding_model.is_loaded() and _rpc_consumer.is_connected():
        _logger.log("main:readiness", "Embedding readiness changed from false to true", {
            "ready_for_rpc": True,
        })

    try:
        yield
    finally:
        # --- shutdown ---
        _running = False
        _logger.log("main:shutdown", "Embedding service shutting down gracefully", {})
        await _rpc_consumer.stop()
        await _rpc_producer.close()
        for c in [_consumer, _extract_consumer, _job_consumer]:
            try:
                c.close()
            except Exception:
                pass
        for t in threads:
            if t.is_alive():
                t.join(timeout=10.0)
        try:
            _producer.flush()
        except Exception:
            pass
        _logger.log("main:shutdown", "Embedding service shutdown complete", {})


app = FastAPI(title="Embedding Service", lifespan=lifespan)
setup_cors(app)
if _HAS_METRICS:
    setup_metrics(app, "embedding")

app.include_router(create_health_router(
    get_producer=lambda: _producer,
    get_model=lambda: _embedding_model,
    get_rpc_consumer=lambda: _rpc_consumer,
))

if __name__ == "__main__":
    import uvicorn
    cfg = EmbeddingConfig()
    uvicorn.run(app, host=cfg.service_host, port=cfg.service_port)
