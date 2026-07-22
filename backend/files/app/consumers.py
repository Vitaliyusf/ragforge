"""Background consumer thread for the files service.

The ``run`` function is started as a daemon thread in ``main.lifespan`` and
consumes messages from the configured ``files.requests`` Kafka topic until the
``running`` flag is cleared during shutdown.
"""
import time
from typing import Callable

from app.messaging.interfaces import IConsumer
from app.services.file_service import FileService


def run(
    consumer: IConsumer,
    file_service: FileService,
    logger,
    topic: str,
    is_running: Callable[[], bool],
) -> None:
    """Consume ``files.requests`` messages until ``is_running()`` returns False.

    Args:
        consumer: Initialized Kafka consumer subscribed to the request topic.
        file_service: Service that dispatches each incoming action.
        logger: Service logger instance.
        topic: Topic name used in log messages only.
        is_running: Zero-argument callable; loop exits when it returns False.
    """
    logger.log("consumers:run", "Files request consumer started", {"topic": topic})
    request_count = 0

    while is_running():
        try:
            for message in consumer.consume():
                request_count += 1
                logger.log(
                    "consumers:run",
                    "Processing file request",
                    {
                        "request_count": request_count,
                        "action": message.get("action", "N/A"),
                        "correlation_id": message.get("correlation_id"),
                    },
                )
                file_service.process_request(message)
                logger.log(
                    "consumers:run",
                    "File request completed",
                    {"request_count": request_count},
                )
        except RuntimeError as e:
            logger.log(
                "consumers:run",
                "Consumer not initialized, waiting",
                {"error": str(e)},
                hypothesis_id="W",
            )
            time.sleep(2)
        except StopIteration:
            continue
        except Exception as e:
            logger.log(
                "consumers:run",
                "Consumer error, reinitializing",
                {"error": str(e), "error_type": type(e).__name__},
                hypothesis_id="E",
            )
            time.sleep(2)
