"""Shared Kafka producer and consumer base classes.

All backend services use the same retry-capable Kafka producer and consumer
pattern. This module provides the base classes so that pattern is defined
once and each service only declares what is different (group_id, offset_reset).

Usage in a service::

    from shared.kafka_base import BaseKafkaProducer, BaseKafkaConsumer
    from app.messaging.interfaces import IProducer, IConsumer
    from app.core.config import Settings


    class KafkaProducerImpl(BaseKafkaProducer, IProducer):
        pass


    class KafkaConsumerImpl(BaseKafkaConsumer, IConsumer):
        def __init__(self, config: Settings, topic: str, group_id: str | None = None):
            super().__init__(
                config,
                topic,
                group_id=group_id or f"{config.service_name}_{topic}_consumer",
            )
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterator, Optional, Tuple

from kafka import KafkaConsumer, KafkaProducer
from kafka.structs import TopicPartition
from .auth import attach_internal_auth_context
from .metrics import METRICS, observe_kafka_consumer_lag

logger = logging.getLogger(__name__)


def _broker_connected(client: Any) -> bool:
    """Return whether ``client`` holds a live connection to at least one broker.

    ``bootstrap_connected()`` alone stopped being a readiness signal in
    kafka-python 2.2: the client now closes the bootstrap connection as soon as
    it has real broker metadata, so a perfectly healthy producer or consumer
    reports False from its first poll onwards. The brokers the client is
    actually talking to are what readiness means.
    """
    if client is None:
        return False
    try:
        return any(client.connected(broker.nodeId) for broker in client.cluster.brokers())
    except Exception:
        return False


class _KafkaConfigProtocol:
    """Structural interface required by both base classes.

    Every service config must expose these Kafka fields.
    No import of this class is required — Python's duck typing handles it.
    """

    kafka_bootstrap_servers: str
    service_name: str
    kafka_max_retries: int
    kafka_retry_delay: int
    kafka_consumer_timeout_ms: int
    kafka_api_version: Tuple[int, int, int]


class BaseKafkaProducer:
    """Retry-capable Kafka producer shared by all backend services.

    Subclass this and mix in the service-specific ``IProducer`` interface::

        class KafkaProducerImpl(BaseKafkaProducer, IProducer):
            pass
    """

    def __init__(self, config: _KafkaConfigProtocol) -> None:
        self.config = config
        self._producer: Optional[KafkaProducer] = None

    # ------------------------------------------------------------------
    # Internal lifecycle
    # ------------------------------------------------------------------

    def _init_producer(self) -> bool:
        """Lazily initialize the Kafka producer with retry logic."""
        if self._producer is not None:
            return True

        for attempt in range(self.config.kafka_max_retries):
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=self.config.kafka_bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    api_version=self.config.kafka_api_version,
                )
                return True
            except Exception as exc:
                if attempt < self.config.kafka_max_retries - 1:
                    logger.warning(
                        "Kafka producer init failed (attempt %d/%d): %s. Retrying...",
                        attempt + 1,
                        self.config.kafka_max_retries,
                        exc,
                    )
                    time.sleep(self.config.kafka_retry_delay)
                else:
                    logger.error(
                        "Failed to initialize Kafka producer after %d attempts: %s",
                        self.config.kafka_max_retries,
                        exc,
                    )
                    return False
        return False

    # ------------------------------------------------------------------
    # IProducer interface
    # ------------------------------------------------------------------

    def send(self, topic: str, message: Dict[str, Any]) -> None:
        """Serialize and publish a message to a Kafka topic."""
        if not self._init_producer() or self._producer is None:
            raise RuntimeError("Kafka producer not available")
        attach_internal_auth_context(message)
        self._producer.send(topic, message)

    def flush(self) -> None:
        """Flush any buffered messages."""
        if self._producer:
            self._producer.flush()

    def is_connected(self) -> bool:
        """Return whether the producer currently has a live broker connection."""
        producer = self._producer
        if producer is None:
            return False
        if producer.bootstrap_connected():
            return True
        sender = getattr(producer, "_sender", None)
        return _broker_connected(getattr(sender, "_client", None))


class BaseKafkaConsumer:
    """Retry-capable Kafka consumer shared by all backend services.

    Subclasses pass the config and resolve the ``group_id`` in ``__init__``
    before calling ``super().__init__()``::

        class KafkaConsumerImpl(BaseKafkaConsumer, IConsumer):
            def __init__(self, config: Settings, topic: str, group_id: str | None = None):
                super().__init__(
                    config,
                    topic,
                    group_id=group_id or f"{config.service_name}_{topic}_consumer",
                )

    Pass ``auto_offset_reset="latest"`` for services (e.g. gateway) that only
    want messages produced after startup.
    """

    def __init__(
        self,
        config: _KafkaConfigProtocol,
        topic: str,
        group_id: str,
        *,
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = True,
    ) -> None:
        self.config = config
        self.topic = topic
        self.group_id = group_id
        self.auto_offset_reset = auto_offset_reset
        self.enable_auto_commit = enable_auto_commit
        self._consumer: Optional[KafkaConsumer] = None

    # ------------------------------------------------------------------
    # Internal lifecycle
    # ------------------------------------------------------------------

    def _init_consumer(self) -> bool:
        """Lazily initialize the Kafka consumer with retry logic."""
        if self._consumer is not None:
            return True

        for attempt in range(self.config.kafka_max_retries):
            try:
                self._consumer = KafkaConsumer(
                    self.topic,
                    bootstrap_servers=self.config.kafka_bootstrap_servers,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    auto_offset_reset=self.auto_offset_reset,
                    consumer_timeout_ms=self.config.kafka_consumer_timeout_ms,
                    group_id=self.group_id,
                    enable_auto_commit=self.enable_auto_commit,
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
        """Yield decoded messages from the configured Kafka topic.

        Processing duration is timed across the ``yield``: the generator hands
        a message to the caller and the clock stops when the caller comes back
        for the next one, so the histogram measures the consumer's own work
        rather than the broker's. Measured here because this is the single
        boundary every Kafka consumer in the repository already goes through.
        """
        if not self._init_consumer() or self._consumer is None:
            raise RuntimeError("Kafka consumer not available")
        service = str(getattr(self.config, "service_name", "unknown"))
        try:
            for message in self._consumer:
                self._record_lag(message)
                started = time.perf_counter()
                try:
                    yield message.value
                finally:
                    # `finally`, so a handler that raises or a caller that
                    # abandons the generator still records the work it did.
                    METRICS.kafka_message_processing_duration.labels(
                        service=service, topic=message.topic
                    ).observe(max(0.0, time.perf_counter() - started))
        except StopIteration:
            return

    def _record_lag(self, message: Any) -> None:
        """Update the consumer-lag gauge from offsets this fetch already carried.

        Free: ``highwater`` is the value kafka-python cached from the last
        FetchResponse, so this adds no broker round-trip, no admin client, and
        no background thread — the gauge is updated on the path that was
        already running.

        Never raises. Lag is a monitoring side-effect of consuming, and a
        metrics failure must not stop a service from processing its messages.
        """
        if self._consumer is None:
            return
        try:
            partition = TopicPartition(message.topic, message.partition)
            observe_kafka_consumer_lag(
                service=getattr(self.config, "service_name", "unknown"),
                topic=message.topic,
                group=self.group_id,
                highwater=self._consumer.highwater(partition),
                # Both are *next* offsets: the message just yielded is consumed.
                next_offset=message.offset + 1,
            )
        except Exception:
            logger.debug("Kafka consumer lag not recorded", exc_info=True)

    def close(self) -> None:
        """Close the consumer and release the underlying client."""
        if self._consumer:
            self._consumer.close()
            self._consumer = None

    def is_connected(self) -> bool:
        """Return whether the consumer currently has a live broker connection."""
        consumer = self._consumer
        if consumer is None:
            return False
        if consumer.bootstrap_connected():
            return True
        return _broker_connected(getattr(consumer, "_client", None))
