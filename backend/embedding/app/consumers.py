"""Background Kafka consumer loop functions for the embedding service.

Each function is intended to run in a daemon thread started by the lifespan
context manager in main.py. They loop until the module-level _running flag is
cleared at shutdown.
"""
import time
from shared.auth import verify_internal_ticket_from_envelope
from shared.context import bound_context


def _authenticated(message):
    identity = verify_internal_ticket_from_envelope(message)
    context = identity.to_dict() if identity is not None else {}
    context.update({
        "request_id": message.get("request_id"),
        "trace_id": message.get("trace_id"),
        "correlation_id": message.get("correlation_id"),
    })
    return bound_context(**context)


def process_embedding_requests(consumer, handler, logger, config, running_flag):
    """Run the legacy embedding consumer loop until shutdown."""
    logger.log("consumers:embedding", "Starting embedding request processing", {"topic": config.request_topic})
    request_count = 0
    while running_flag():
        try:
            for message in consumer.consume():
                request_count += 1
                logger.log(
                    "consumers:embedding",
                    "Processing embedding request",
                    {"request_num": request_count},
                )
                with _authenticated(message):
                    handler.process_request(message)
                logger.log(
                    "consumers:embedding",
                    "Embedding request completed",
                    {"request_num": request_count},
                )
        except RuntimeError as e:
            logger.log("consumers:embedding", "Consumer not initialized, waiting...", {"error": str(e)})
            time.sleep(2)
        except StopIteration:
            continue
        except Exception as e:
            logger.log(
                "consumers:embedding",
                "Consumer error, reinitializing",
                {"error": str(e), "error_type": type(e).__name__},
                hypothesis_id="E",
            )
            time.sleep(2)


def process_embedding_job_requests(job_consumer, worker, logger, config, running_flag):
    """Run the typed embedding-job consumer loop until shutdown."""
    logger.log(
        "consumers:embedding_jobs",
        "Starting embedding job processing",
        {"topic": config.embedding_jobs_requested_topic},
    )
    request_count = 0
    while running_flag():
        try:
            for message in job_consumer.consume():
                request_count += 1
                payload = message.get("payload", {})
                logger.log(
                    "consumers:embedding_jobs",
                    "Processing embedding job",
                    {
                        "request_num": request_count,
                        "message_id": message.get("message_id"),
                        "request_id": message.get("request_id"),
                        "job_id": payload.get("job_id"),
                        "file_id": payload.get("file_id"),
                        "document_id": payload.get("document_id"),
                    },
                )
                with _authenticated(message):
                    worker.handle_message(message)
                logger.log(
                    "consumers:embedding_jobs",
                    "Embedding job completed",
                    {
                        "request_num": request_count,
                        "message_id": message.get("message_id"),
                        "job_id": payload.get("job_id"),
                    },
                )
        except RuntimeError as e:
            logger.log(
                "consumers:embedding_jobs",
                "Embedding job consumer not initialized, waiting...",
                {"error": str(e)},
            )
            time.sleep(2)
        except StopIteration:
            continue
        except Exception as e:
            logger.log(
                "consumers:embedding_jobs",
                "Embedding job consumer error, reinitializing",
                {"error": str(e), "error_type": type(e).__name__},
                hypothesis_id="E",
            )
            time.sleep(2)


def process_extraction_requests(extract_consumer, handler, logger, config, running_flag):
    """Run the legacy extraction consumer loop until shutdown."""
    logger.log("consumers:extraction", "Starting extraction request processing", {"topic": config.extract_topic})
    request_count = 0
    while running_flag():
        try:
            for message in extract_consumer.consume():
                request_count += 1
                logger.log(
                    "consumers:extraction",
                    "Processing extraction request",
                    {"request_num": request_count, "file_id": message.get("file_id")},
                )
                with _authenticated(message):
                    handler.process_request(message)
                logger.log(
                    "consumers:extraction",
                    "Extraction request completed",
                    {"request_num": request_count},
                )
        except RuntimeError as e:
            logger.log("consumers:extraction", "Extract consumer not initialized, waiting...", {"error": str(e)})
            time.sleep(2)
        except StopIteration:
            continue
        except Exception as e:
            logger.log(
                "consumers:extraction",
                "Extract consumer error, reinitializing",
                {"error": str(e), "error_type": type(e).__name__},
                hypothesis_id="E",
            )
            time.sleep(2)
