"""FastAPI entrypoint for the vector_db service."""
from contextlib import asynccontextmanager
from typing import Optional
from functools import partial

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
from shared.kafka_workers import KafkaConsumerWorkerPool
from app.db.interfaces import IVectorStore
from app.db.session import get_vector_store
from app.messaging.factories import MessageQueueFactory
from app.messaging.implementations.kafka import VectorDbKafkaConsumer, VectorDbKafkaProducer
from app.messaging.implementations.rabbitmq import RabbitMQConsumerImpl
from app.rest.routes import api_router
from app.services.vector_service import VectorService
from app.utils.common import setup_cors
from app.worker import process_requests

# ---------------------------------------------------------------------------
# Module-level singletons — initialised in lifespan, exposed for deps.py
# ---------------------------------------------------------------------------

_logger: Optional[ServiceLogger] = None
_kafka_producer: Optional[VectorDbKafkaProducer] = None
_kafka_consumer_pool: Optional[KafkaConsumerWorkerPool] = None
_rpc_consumer: Optional[RabbitMQConsumerImpl] = None
_vector_store: Optional[IVectorStore] = None
_vector_service: Optional[VectorService] = None
_running: list[bool] = [False]  # mutable flag shared with worker thread


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _logger, _kafka_producer, _kafka_consumer_pool, _rpc_consumer
    global _vector_store, _vector_service, _running

    # --- startup ---
    _logger = ServiceLogger(settings.service_name)
    _kafka_producer = VectorDbKafkaProducer(settings)
    _vector_store = get_vector_store()
    _vector_service = VectorService(
        vector_store=_vector_store,
        producer=_kafka_producer,
        service_logger=_logger,
        upsert_completed_topic=settings.kafka_upsert_completed_topic,
        files_topic=settings.kafka_files_topic,
        upsert_requested_topic=settings.kafka_upsert_requested_topic,
        delete_requested_topic=settings.kafka_delete_requested_topic,
        service_name=settings.service_name,
    )

    _logger.log("main:startup", "Vector DB service starting up", {
        "service_name": settings.service_name,
        "service_port": settings.service_port,
        "collection_name": _vector_store.collection_name,
        "vector_count": _vector_store.count(),
    })
    _vector_service.initialize_collection()

    # Start Kafka upsert/delete pipeline consumer thread
    _running[0] = True
    _kafka_consumer_pool = KafkaConsumerWorkerPool(
        worker_count=settings.kafka_pipeline_consumer_workers,
        consumer_factory=lambda: VectorDbKafkaConsumer(
            settings,
            [
                settings.kafka_upsert_requested_topic,
                settings.kafka_delete_requested_topic,
            ],
        ),
        target_factory=lambda consumer: partial(
            process_requests,
            consumer,
            _vector_service,
            _logger,
            _running,
        ),
        thread_name_prefix="VectorDBKafkaConsumer",
    ).start()
    _logger.log("main:startup", "Kafka pipeline consumer workers started")

    # Start RabbitMQ RPC consumer
    _rpc_consumer = MessageQueueFactory.create_consumer(settings)
    executor = BoundedExecutor(
        service=settings.service_name,
        pool="rpc",
        max_workers=settings.executor_workers,
        queue_bound=settings.executor_queue_bound,
        submit_timeout_seconds=settings.executor_submit_timeout_seconds,
    )

    async def _handle(body: dict, reply_to: str, correlation_id: str):
        body = dict(body)  # shallow copy
        body.setdefault("reply_to", reply_to)
        body.setdefault("correlation_id", correlation_id)
        return await executor.run(
            _vector_service.process_request,
            body,
            stage="vector_search",
        )

    try:
        await _rpc_consumer.start(_handle)
        _logger.log("main:startup", "RabbitMQ RPC consumer started")
        yield
    finally:
        # --- shutdown ---
        _logger.log("main:shutdown", "Vector DB service shutting down gracefully")

        # Stop RabbitMQ RPC consumer
        await _rpc_consumer.stop()
        await executor.shutdown()
        _vector_service.close()

        # Stop Kafka pipeline consumer thread
        _running[0] = False
        _kafka_consumer_pool.close(timeout=10.0)
        try:
            _kafka_producer.flush()
        except Exception:
            pass
        if _vector_store is not None:
            _vector_store.close()

        _logger.log("main:shutdown", "Shutdown complete")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Vector DB Service",
    description="Chunk-native vector database service with RabbitMQ RPC and Kafka pipeline",
    version="2.0.0",
    lifespan=lifespan,
)

setup_cors(app)
register_exception_handlers(app)

if _HAS_METRICS:
    setup_metrics(app, "vector_db")

app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.service_host, port=settings.service_port)
