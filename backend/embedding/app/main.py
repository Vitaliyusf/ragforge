"""FastAPI entrypoint for query embeddings and typed passage jobs."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from threading import Event, Thread
from typing import Any

from fastapi import FastAPI

try:
    from shared.metrics import setup_metrics

    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

from app.config import EmbeddingConfig
from app.consumers import process_embedding_job_requests, process_extraction_requests
from app.core.cors import setup_cors
from app.embedding.factories import EmbeddingModelFactory
from app.extraction.factories import FileExtractorFactory
from app.messaging.embedding_kafka import EmbeddingKafkaConsumer, EmbeddingKafkaProducer
from app.messaging.factories import MessageQueueFactory
from app.messaging.threadsafe_rabbitmq import ThreadsafeRabbitMQPublisher
from app.rest.v1.health import create_health_router
from app.services.embedding_handler import QueryEmbeddingHandler
from app.services.embedding_job_service import EmbeddingJobService
from app.services.embedding_job_tracing import EmbeddingLangSmithTracer
from app.services.embedding_job_worker import EmbeddingJobConsumerWorker
from app.services.extraction_handler import ExtractionHandler
from shared.logging import ServiceLogger
from shared.bounded_executor import BoundedExecutor


@dataclass
class EmbeddingRuntime:
    """Clients and workers whose lifetime is owned by the FastAPI app."""

    producer: Any
    model: Any
    rpc_consumer: Any
    rpc_producer: Any
    extract_consumer: Any
    job_consumer: Any
    stop_event: Event
    threads: list[Thread]


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = EmbeddingConfig()
    logger = ServiceLogger(config.service_name)
    producer = MessageQueueFactory.create_producer(config)
    rpc_producer = MessageQueueFactory.create_rabbitmq_producer(config)
    await rpc_producer.connect()
    rpc_publisher = ThreadsafeRabbitMQPublisher(
        rpc_producer,
        asyncio.get_running_loop(),
    )
    extract_consumer = MessageQueueFactory.create_consumer(config, config.extract_topic)
    job_consumer = EmbeddingKafkaConsumer(config)
    job_producer = EmbeddingKafkaProducer(
        producer=producer,
        upsert_topic=config.vector_db_upsert_requested_topic,
        completed_topic=config.embedding_jobs_completed_topic,
    )

    model = EmbeddingModelFactory.create(config)
    if model is None:
        logger.log("main:startup", "No embedding model available", {}, hypothesis_id="W")

    extractors = FileExtractorFactory.create_all()
    if not extractors:
        logger.log("main:startup", "No file extractors available", {}, hypothesis_id="W")

    tracer = EmbeddingLangSmithTracer(
        enabled=config.langsmith_tracing,
        api_key=config.langsmith_api_key,
        project=config.langsmith_project,
    )
    job_service = EmbeddingJobService(
        producer=job_producer,
        embedding_model=model,
        logger=logger,
        config=config,
        tracer=tracer,
    )
    job_worker = EmbeddingJobConsumerWorker(job_consumer, job_service, logger)
    query_handler = QueryEmbeddingHandler(model, logger, config)
    extraction_handler = ExtractionHandler(
        producer,
        extractors,
        logger,
        config.files_topic,
        config.summary_topic,
        config.metadata_topic,
        config,
        rpc_producer=rpc_publisher,
    )

    stop_event = Event()
    threads = [
        Thread(
            target=partial(
                process_embedding_job_requests,
                job_consumer,
                job_worker,
                logger,
                config,
                stop_event,
            ),
            daemon=True,
            name="EmbeddingJobConsumer",
        ),
        Thread(
            target=partial(
                process_extraction_requests,
                extract_consumer,
                extraction_handler,
                logger,
                config,
                stop_event,
            ),
            daemon=True,
            name="ExtractionConsumer",
        ),
    ]
    for thread in threads:
        thread.start()

    rpc_consumer = MessageQueueFactory.create_rabbitmq_consumer(config)
    executor = BoundedExecutor(
        service=config.service_name,
        pool="query",
        max_workers=config.executor_workers,
        queue_bound=config.executor_queue_bound,
        submit_timeout_seconds=config.executor_submit_timeout_seconds,
    )

    async def handle_rpc(body, reply_to, correlation_id):
        return await executor.run(
            query_handler.process_request_with_reply,
            body,
            reply_to,
            correlation_id,
            stage="embedding_query",
        )

    await rpc_consumer.start(handle_rpc)
    runtime = EmbeddingRuntime(
        producer=producer,
        model=model,
        rpc_consumer=rpc_consumer,
        rpc_producer=rpc_producer,
        extract_consumer=extract_consumer,
        job_consumer=job_consumer,
        stop_event=stop_event,
        threads=threads,
    )
    app.state.embedding_runtime = runtime
    logger.log(
        "main:startup",
        "Embedding service started",
        {
            "query_transport": "rabbitmq",
            "passage_job_topic": config.embedding_jobs_requested_topic,
            "extraction_topic": config.extract_topic,
            "model_loaded": model.is_loaded() if model else False,
            "extractors_count": len(extractors),
        },
    )

    try:
        yield
    finally:
        logger.log("main:shutdown", "Embedding service shutting down", {})
        stop_event.set()
        await rpc_consumer.stop()
        await executor.shutdown()
        await rpc_producer.close()
        for consumer in (extract_consumer, job_consumer):
            try:
                consumer.close()
            except Exception:
                logger.log(
                    "main:shutdown",
                    "Consumer close failed",
                    {"consumer": type(consumer).__name__},
                    hypothesis_id="W",
                )
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=10.0)
        try:
            producer.flush()
        except Exception:
            logger.log(
                "main:shutdown",
                "Kafka producer flush failed",
                {},
                hypothesis_id="W",
            )
        app.state.embedding_runtime = None
        logger.log("main:shutdown", "Embedding service shutdown complete", {})


app = FastAPI(title="Embedding Service", lifespan=lifespan)
setup_cors(app)
if _HAS_METRICS:
    setup_metrics(app, "embedding")


def _runtime_dependency(name: str):
    runtime = getattr(app.state, "embedding_runtime", None)
    return getattr(runtime, name, None)


app.include_router(
    create_health_router(
        get_producer=lambda: _runtime_dependency("producer"),
        get_model=lambda: _runtime_dependency("model"),
        get_rpc_consumer=lambda: _runtime_dependency("rpc_consumer"),
    )
)

if __name__ == "__main__":
    import uvicorn

    cfg = EmbeddingConfig()
    uvicorn.run(app, host=cfg.service_host, port=cfg.service_port)
