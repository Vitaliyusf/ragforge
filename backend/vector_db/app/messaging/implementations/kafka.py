"""Kafka implementation of message queue interfaces for vector_db."""
import json
import logging
import time
from typing import Any, Dict, Iterator, List, Optional

from kafka import KafkaConsumer

from shared.kafka_base import BaseKafkaProducer, kafka_document_key

from app.messaging.interfaces import IConsumer, IProducer
from app.core.config import Settings

logger = logging.getLogger(__name__)


class VectorDbKafkaProducer(BaseKafkaProducer, IProducer):
    """Kafka producer for vector_db with domain-specific convenience methods."""

    def __init__(self, config: Settings) -> None:
        super().__init__(config)

    def send_reply(self, reply_to: str, message: Dict[str, Any]) -> None:
        """Send a direct reply to a caller-provided topic."""
        self.send(reply_to, message)

    def publish_upsert_completed(self, message: Dict[str, Any]) -> None:
        """Publish the completion event for an upsert request."""
        self.send(
            self.config.kafka_upsert_completed_topic,
            message,
            key=kafka_document_key(message),
        )


class VectorDbKafkaConsumer(IConsumer):
    """Kafka consumer that subscribes to multiple topics.

    Yields messages wrapped in a ``{"topic": ..., "message": ...}`` envelope
    so the caller knows which topic each message arrived on.
    """

    def __init__(
        self,
        config: Settings,
        topics: List[str],
        group_id: Optional[str] = None,
    ) -> None:
        self.config = config
        self.topics = list(dict.fromkeys(topics))  # deduplicate, preserve order
        self.group_id = group_id or f"{config.service_name}_consumer"
        self._consumer: Optional[KafkaConsumer] = None

    # ------------------------------------------------------------------
    # Internal lifecycle
    # ------------------------------------------------------------------

    def _init_consumer(self, timeout_ms: Optional[int] = None) -> bool:
        if self._consumer is not None:
            return True

        consumer_timeout_ms = timeout_ms or self.config.kafka_consumer_timeout_ms

        for attempt in range(self.config.kafka_max_retries):
            try:
                self._consumer = KafkaConsumer(
                    *self.topics,
                    bootstrap_servers=self.config.kafka_bootstrap_servers,
                    value_deserializer=lambda payload: json.loads(payload.decode("utf-8")),
                    auto_offset_reset="earliest",
                    consumer_timeout_ms=consumer_timeout_ms,
                    group_id=self.group_id,
                    enable_auto_commit=True,
                )
                return True
            except Exception as exc:
                if attempt < self.config.kafka_max_retries - 1:
                    logger.warning(
                        "Kafka consumer init failed (attempt %d/%d): %s. Retrying...",
                        attempt + 1,
                        self.config.kafka_max_retries,
                        exc,
                    )
                    time.sleep(self.config.kafka_retry_delay)
                else:
                    logger.error(
                        "Failed to initialize Kafka consumer after %d attempts: %s",
                        self.config.kafka_max_retries,
                        exc,
                    )
                    return False
        return False

    # ------------------------------------------------------------------
    # IConsumer interface
    # ------------------------------------------------------------------

    def consume(self, timeout_ms: int = 1000) -> Iterator[Dict[str, Any]]:
        if not self._init_consumer(timeout_ms):
            raise RuntimeError("Kafka consumer not available")
        try:
            for message in self._consumer:
                yield {"topic": message.topic, "message": message.value}
        except StopIteration:
            return

    def close(self) -> None:
        if self._consumer:
            self._consumer.close()
            self._consumer = None

    def is_connected(self) -> bool:
        return self._consumer is not None
