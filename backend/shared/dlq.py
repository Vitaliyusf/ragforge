"""Dead Letter Queue (DLQ) helper for failed Kafka messages.

When a message handler fails repeatedly, the message is published to a
service-specific DLQ topic instead of being silently dropped. Failed
messages are also stored in MongoDB for inspection and replay.

Usage:
    dlq = DeadLetterQueue(producer=kafka_producer, service_name="rag")

    try:
        handler.handle(message)
    except Exception as e:
        dlq.send(message, error=e, max_retries=3)
"""
import traceback
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger("dlq")


class DeadLetterQueue:
    """
    Publishes failed messages to a DLQ topic and optionally stores them in MongoDB.

    DLQ topic naming convention: {service_name}_dlq
    MongoDB collection: dlq_messages

    Each DLQ entry includes:
    - Original message payload
    - Error details (type, message, traceback)
    - Service name and timestamp
    - Retry count
    - Processing metadata (correlation_id, original_topic)
    """

    def __init__(
        self,
        producer: Any,
        service_name: str,
        db_collection: Any = None,
    ):
        """
        Args:
            producer: Kafka producer (IProducer interface)
            service_name: Name of the service (e.g., "rag", "embedding")
            db_collection: Optional MongoDB collection for persistent DLQ storage
        """
        self.producer = producer
        self.service_name = service_name
        self.db_collection = db_collection
        self.topic = f"{service_name}_dlq"

        # Metrics
        self._total_sent = 0
        self._total_by_error_type: Dict[str, int] = {}

    def send(
        self,
        original_message: Dict[str, Any],
        error: Exception,
        original_topic: Optional[str] = None,
        retry_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send a failed message to the DLQ.

        Args:
            original_message: The original Kafka message that failed
            error: The exception that caused the failure
            original_topic: The topic the message was consumed from
            retry_count: Number of times this message was retried
            metadata: Additional context about the failure

        Returns:
            The DLQ entry that was published
        """
        error_type = type(error).__name__

        dlq_entry = {
            "service": self.service_name,
            "original_topic": original_topic or "unknown",
            "original_message": self._sanitize_message(original_message),
            "correlation_id": original_message.get("correlation_id"),
            "error": {
                "type": error_type,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
            "retry_count": retry_count,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "unprocessed",
        }

        # Publish to Kafka DLQ topic
        try:
            self.producer.send(self.topic, dlq_entry)
            self.producer.flush()
            logger.warning(
                f"Message sent to DLQ topic '{self.topic}': "
                f"correlation_id={dlq_entry['correlation_id']}, "
                f"error={error_type}: {error}"
            )
        except Exception as kafka_err:
            logger.error(
                f"Failed to publish to DLQ topic '{self.topic}': {kafka_err}"
            )

        # Persist to MongoDB if collection is available
        if self.db_collection is not None:
            try:
                self.db_collection.insert_one(dlq_entry.copy())
            except Exception as db_err:
                logger.error(f"Failed to persist DLQ entry to MongoDB: {db_err}")

        # Update metrics
        self._total_sent += 1
        self._total_by_error_type[error_type] = (
            self._total_by_error_type.get(error_type, 0) + 1
        )

        return dlq_entry

    def _sanitize_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize the original message for DLQ storage.
        Truncates large fields (e.g., embeddings, long text) to prevent
        bloating the DLQ.
        """
        sanitized: Dict[str, Any] = {}
        for key, value in message.items():
            if isinstance(value, list) and len(value) > 50:
                sanitized[key] = f"[list of {len(value)} items, truncated]"
            elif isinstance(value, str) and len(value) > 5000:
                sanitized[key] = value[:5000] + f"... [truncated, total {len(value)} chars]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_message(value)
            else:
                sanitized[key] = value
        return sanitized

    @property
    def metrics(self) -> Dict[str, Any]:
        """DLQ metrics for monitoring."""
        return {
            "service": self.service_name,
            "topic": self.topic,
            "total_sent": self._total_sent,
            "by_error_type": dict(self._total_by_error_type),
        }


class DLQAwareHandler:
    """
    Mixin that adds DLQ support to message handlers.

    Tracks per-message failure counts and sends to DLQ after max_retries.
    Extend alongside BaseKafkaHandler:

        class MyHandler(BaseKafkaHandler, DLQAwareHandler):
            def handle(self, message):
                try:
                    self._process(message)
                except Exception as e:
                    self.handle_with_dlq(message, e, "my_topic")
    """

    def init_dlq(self, dlq: DeadLetterQueue, max_retries: int = 3) -> None:
        """Initialize DLQ support on this handler."""
        self._dlq = dlq
        self._dlq_max_retries = max_retries
        self._failure_counts: Dict[str, int] = {}

    def handle_with_dlq(
        self,
        message: Dict[str, Any],
        error: Exception,
        original_topic: str,
    ) -> bool:
        """
        Handle a message failure with DLQ escalation.

        Returns:
            True if message was sent to DLQ (exhausted retries),
            False if it can still be retried.
        """
        correlation_id = message.get("correlation_id", "unknown")
        self._failure_counts[correlation_id] = (
            self._failure_counts.get(correlation_id, 0) + 1
        )
        count = self._failure_counts[correlation_id]

        if count >= self._dlq_max_retries:
            self._dlq.send(
                original_message=message,
                error=error,
                original_topic=original_topic,
                retry_count=count,
            )
            # Clean up tracking
            self._failure_counts.pop(correlation_id, None)
            return True

        logger.warning(
            f"Message {correlation_id} failed (attempt {count}/{self._dlq_max_retries}): {error}"
        )
        return False
