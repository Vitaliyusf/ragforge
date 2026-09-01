"""FastAPI entrypoint for query embeddings and typed passage jobs."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from threading import Event
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
from app.services.inference_scheduler import create_scheduler
from shared.logging import ServiceLogger
from shared.bounded_executor import BoundedExecutor
from shared.kafka_workers import KafkaConsumerWorkerPool


@dataclass
class EmbeddingRuntime:
    """Clients and workers whose lifetime is owned by the FastAPI app."""

    producer: Any
    model: Any
    scheduler: Any
    rpc_consumer: Any
    rpc_producer: Any
    stop_event: Event
    consumer_pools: list[KafkaConsumerWorkerPool]


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
    job_producer = EmbeddingKafkaProducer(
        producer=producer,
        upsert_topic=config.vector_db_upsert_requested_topic,
        completed_topic=config.embedding_jobs_completed_topic,
    )

    model = EmbeddingModelFactory.create(config)
    if model is None:
        logger.log("main:startup", "No embedding model available", {}, hypothesis_id="W")

    # One model, one scheduler, one process. Every embedding path below hands
    # logical items to this object; nothing else calls the model.
    scheduler = create_scheduler(model, config, logger).start()

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
        scheduler=scheduler,
        logger=logger,
        config=config,
        tracer=tracer,
    )
    query_handler = QueryEmbeddingHandler(scheduler, logger, config)
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
    job_consumer_pool = KafkaConsumerWorkerPool(
        worker_count=config.kafka_pipeline_consumer_workers,
        consumer_factory=lambda: EmbeddingKafkaConsumer(config),
        target_factory=lambda consumer: partial(
                process_embedding_job_requests,
                consumer,
                EmbeddingJobConsumerWorker(consumer, job_service, logger),
                logger,
                config,
                stop_event,
        ),
        thread_name_prefix="EmbeddingJobConsumer",
    ).start()
    extraction_consumer_pool = KafkaConsumerWorkerPool(
        worker_count=config.kafka_pipeline_consumer_workers,
        consumer_factory=lambda: MessageQueueFactory.create_consumer(
            config,
            config.extract_topic,
        ),
        target_factory=lambda consumer: partial(
                process_extraction_requests,
                consumer,
                extraction_handler,
                logger,
                config,
                stop_event,
        ),
        thread_name_prefix="ExtractionConsumer",
    ).start()
    consumer_pools = [job_consumer_pool, extraction_consumer_pool]

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
        scheduler=scheduler,
        rpc_consumer=rpc_consumer,
        rpc_producer=rpc_producer,
        stop_event=stop_event,
        consumer_pools=consumer_pools,
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
            "microbatch_window_ms": config.embedding_microbatch_window_ms,
            "max_batch_size": scheduler.max_batch_size,
            "max_pending_items": scheduler.max_pending_items,
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
        for consumer_pool in consumer_pools:
            if not consumer_pool.close(timeout=10.0):
                logger.log(
                    "main:shutdown",
                    "Kafka consumer workers did not stop before deadline",
                    {},
                    hypothesis_id="W",
                )
        if not scheduler.shutdown():
            logger.log(
                "main:shutdown",
                "Embedding scheduler failed pending work at shutdown",
                {},
                hypothesis_id="W",
            )
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
