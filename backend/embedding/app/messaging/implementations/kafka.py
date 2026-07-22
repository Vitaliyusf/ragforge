"""Kafka implementation of message queue interfaces for embedding."""
from typing import Optional

from shared.kafka_base import BaseKafkaConsumer, BaseKafkaProducer

from app.messaging.interfaces import IConsumer, IProducer
from app.config import EmbeddingConfig


class KafkaProducerImpl(BaseKafkaProducer, IProducer):
    """Kafka producer for embedding."""

    def __init__(self, config: EmbeddingConfig) -> None:
        super().__init__(config)


class KafkaConsumerImpl(BaseKafkaConsumer, IConsumer):
    """Kafka consumer for embedding."""

    def __init__(self, config: EmbeddingConfig, topic: str, group_id: Optional[str] = None) -> None:
        super().__init__(
            config,
            topic,
            group_id=group_id or f"{config.service_name}_{topic}_consumer",
        )
