"""Background Kafka consumer loop for the vector_db service.

Extracted from main.py to keep the entrypoint ≤ 150 lines.
The loop runs in a daemon thread started by the lifespan handler.
"""
import time
from shared.auth import verify_internal_ticket_from_envelope
from shared.context import bound_context

from shared.logging import ServiceLogger
from app.messaging.interfaces import IConsumer
from app.services.vector_service import VectorService


def process_requests(
    consumer: IConsumer,
    vector_service: VectorService,
    logger: ServiceLogger,
    running: list[bool],
) -> None:
    """Consume Kafka messages and dispatch them to the vector service.

    Args:
        consumer: Kafka consumer subscribing to all vector_db topics.
        vector_service: Handles the actual vector operations.
        logger: Structured service logger.
        running: Single-element list used as a mutable boolean flag.
                 The lifespan handler sets running[0] = False on shutdown.
    """
    logger.log("worker:process_requests", "Starting request processing thread")
    request_count = 0

    while running[0]:
        try:
            for envelope in consumer.consume():
                request_count += 1
                topic = envelope.get("topic", "unknown")
                message = envelope.get("message", {})
                logger.log(
                    "worker:process_requests",
                    f"Received request #{request_count}",
                    {"topic": topic, "action": message.get("action", "N/A")},
                )
                identity = verify_internal_ticket_from_envelope(message)
                context = identity.to_dict() if identity is not None else {}
                context.update({
                    "request_id": message.get("request_id"),
                    "trace_id": message.get("trace_id"),
                    "correlation_id": message.get("correlation_id"),
                })
                with bound_context(**context):
                    vector_service.process_kafka_message(topic, message)
                logger.log(
                    "worker:process_requests",
                    f"Request #{request_count} processing completed",
                    {"topic": topic},
                )
        except RuntimeError:
            logger.log("worker:process_requests", "Consumer not initialized, waiting...")
            time.sleep(2)
        except StopIteration:
            continue
        except Exception as exc:
            logger.log(
                "worker:process_requests",
                "Consumer error, retrying",
                {"error": str(exc), "error_type": type(exc).__name__},
                hypothesis_id="E",
            )
            time.sleep(2)
