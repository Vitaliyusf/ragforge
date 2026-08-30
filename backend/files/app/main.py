"""FastAPI entrypoint for the files service.

Owns all module-level singletons, the lifespan context manager, and app
construction. Business logic, consumer loop, and route handlers live in
dedicated modules.
"""
import os
from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI

try:
    from shared.metrics import setup_metrics
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from shared.logging import ServiceLogger
from shared.bounded_executor import BoundedExecutor
from app.consumers import run as run_pipeline_updates
from app.db.repository import FileRepository
from app.db.session import (
    get_client,
    get_file_audit_events_collection,
    get_file_chunks_collection,
    get_file_review_cases_collection,
    get_file_review_decisions_collection,
    get_file_tasks_collection,
    get_files_collection,
)
from shared.kafka_base import BaseKafkaProducer
from app.messaging.factories import MessageQueueFactory
from app.messaging.implementations.rabbitmq import RabbitMQConsumerImpl
from app.messaging.interfaces import IProducer
from app.rest.routes import api_router
from app.services.file_service import FileService
from app.utils.common import setup_cors


class _KafkaPipelineProducer(BaseKafkaProducer, IProducer):
    """Kafka producer used exclusively for the embedding pipeline (publish-only, not RPC)."""
    pass


# ---------------------------------------------------------------------------
# Module-level singletons (None until lifespan startup initialises them)
# ---------------------------------------------------------------------------
_logger: ServiceLogger = None
_kafka_producer: IProducer = None
_kafka_consumer = None
_consumer: RabbitMQConsumerImpl = None
_consumer_thread: Thread = None
_running = False
_file_repository: FileRepository = None
_file_service: FileService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _logger, _kafka_producer, _kafka_consumer, _consumer, _consumer_thread
    global _file_repository, _file_service, _running

    # --- startup ---
    _logger = ServiceLogger(settings.service_name)
    os.makedirs(settings.upload_dir, exist_ok=True)

    # Kafka producer — kept for embedding pipeline (publishes embedding jobs, not RPC replies)
    _kafka_producer = _KafkaPipelineProducer(settings)

    mongo_client = get_client()
    _file_repository = FileRepository(
        get_files_collection(),
        client=mongo_client,
        logger=_logger,
        file_tasks_collection=get_file_tasks_collection(),
        file_chunks_collection=get_file_chunks_collection(),
        file_review_cases_collection=get_file_review_cases_collection(),
        file_review_decisions_collection=get_file_review_decisions_collection(),
        file_audit_events_collection=get_file_audit_events_collection(),
    )
    _file_repository.ensure_indexes()

    _file_service = FileService(
        producer=_kafka_producer,
        repository=_file_repository,
        logger=_logger,
        config=settings,
    )

    # Kafka remains only for the durable ingestion pipeline. This consumer
    # applies extraction and vector-index stage updates back to file records.
    _kafka_consumer = MessageQueueFactory.create_pipeline_consumer(settings)
    _running = True
    _consumer_thread = Thread(
        target=run_pipeline_updates,
        args=(
            _kafka_consumer,
            _file_service,
            _logger,
            settings.kafka_pipeline_updates_topic,
            lambda: _running,
        ),
        daemon=True,
        name="FilesPipelineConsumer",
    )
    _consumer_thread.start()

    # RabbitMQ consumer for gateway requests (replaces Kafka consumer thread)
    _consumer = MessageQueueFactory.create_consumer(settings)
    executor = BoundedExecutor(
        service=settings.service_name,
        pool="rpc",
        max_workers=settings.executor_workers,
        queue_bound=settings.executor_queue_bound,
        submit_timeout_seconds=settings.executor_submit_timeout_seconds,
    )

    async def _handle(body: dict, reply_to: str, correlation_id: str):
        return await executor.run(
            _file_service.process_request_with_reply,
            body,
            reply_to,
            correlation_id,
            stage="file_ingestion",
        )

    await _consumer.start(_handle)

    _logger.log("main:startup", "Files service started", {
        "service_name": settings.service_name,
        "service_port": settings.service_port,
        "transport": "rabbitmq",
    })

    try:
        yield
    finally:
        # --- shutdown ---
        _logger.log("main:shutdown", "Files service shutting down", {})
        await _consumer.stop()
        await executor.shutdown()
        _running = False
        try:
            _kafka_consumer.close()
        except Exception:
            pass
        if _consumer_thread and _consumer_thread.is_alive():
            _consumer_thread.join(timeout=10.0)
        try:
            _kafka_producer.flush()
        except Exception:
            pass
        _logger.log("main:shutdown", "Files service shutdown complete", {})


# ---------------------------------------------------------------------------
# App construction
# ---------------------------------------------------------------------------
app = FastAPI(title="Files Service", lifespan=lifespan)
setup_cors(app)
register_exception_handlers(app)
if _HAS_METRICS:
    setup_metrics(app, "files")

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.service_host, port=settings.service_port)
