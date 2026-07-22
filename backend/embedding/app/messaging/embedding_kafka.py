"""Kafka wrappers for the embedding job pipeline."""
import json
import logging
import time
from typing import Any, Dict, Iterator, Optional

from kafka import KafkaConsumer

from app.config import EmbeddingConfig
from app.messaging.interfaces import IProducer

logger = logging.getLogger(__name__)


class EmbeddingKafkaProducer:
    """Domain wrapper around the generic Kafka producer."""

    def __init__(self, producer: IProducer, upsert_topic: str, completed_topic: str):
        self._producer = producer
        self._upsert_topic = upsert_topic
        self._completed_topic = completed_topic

    def publish_upsert_requested(self, message: Dict[str, Any]) -> None:
        """Publish a vector_db upsert request."""
        self._producer.send(self._upsert_topic, message)

    def publish_job_completed(self, message: Dict[str, Any]) -> None:
        """Publish an embedding job completion event."""
        self._producer.send(self._completed_topic, message)

    def send(self, topic: str, message: Dict[str, Any]) -> None:
        """Delegate generic send calls for shared utilities like DLQ."""
        self._producer.send(topic, message)

    def flush(self) -> None:
        """Flush pending producer messages."""
        self._producer.flush()

    def is_connected(self) -> bool:
        """Return producer connection state."""
        return self._producer.is_connected()


class EmbeddingKafkaConsumer:
    """Manual-commit Kafka consumer for embedding jobs."""

    def __init__(
        self,
        config: EmbeddingConfig,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> None:
        self.config = config
        self.topic = topic or config.embedding_jobs_requested_topic
        self.group_id = group_id or config.embedding_consumer_group
        self._consumer: Optional[KafkaConsumer] = None

    def _init_consumer(self) -> bool:
        """Initialize the Kafka consumer with retry logic."""
        if self._consumer is not None:
            return True

        for attempt in range(self.config.kafka_max_retries):
            try:
                self._consumer = KafkaConsumer(
                    self.topic,
                    bootstrap_servers=self.config.kafka_bootstrap_servers,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    auto_offset_reset="earliest",
                    consumer_timeout_ms=self.config.kafka_consumer_timeout_ms,
                    group_id=self.group_id,
                    enable_auto_commit=False,
                    max_poll_records=1,
                    api_version=self.config.kafka_api_version,
                )
                return True
            except Exception as exc:
                if attempt < self.config.kafka_max_retries - 1:
                    logger.warning(
                        "Embedding Kafka consumer initialization failed (attempt %d/%d): %s. Retrying...",
                        attempt + 1, self.config.kafka_max_retries, exc,
                    )
                    time.sleep(self.config.kafka_retry_delay)
                else:
                    logger.error(
                        "Failed to initialize embedding Kafka consumer after %d attempts: %s",
                        self.config.kafka_max_retries, exc,
                    )
                    return False
        return False

    def consume(self, timeout_ms: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        """Consume embedding job messages one at a time."""
        if not self._init_consumer():
            raise RuntimeError("Embedding Kafka consumer not available")

        poll_timeout = timeout_ms if timeout_ms is not None else self.config.kafka_consumer_timeout_ms
        records = self._consumer.poll(timeout_ms=poll_timeout, max_records=1)
        for partition_records in records.values():
            for message in partition_records:
                yield message.value

    def commit(self) -> None:
        """Commit the current consumer position."""
        if self._consumer is None:
            raise RuntimeError("Embedding Kafka consumer not initialized")
        self._consumer.commit()

    def close(self) -> None:
        """Close the consumer."""
        if self._consumer:
            self._consumer.close()
            self._consumer = None

    def is_connected(self) -> bool:
        """Return consumer connection state."""
        return self._consumer is not None
