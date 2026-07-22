"""RabbitMQ consumer and producer for the embedding service gateway request queue."""
from shared.rabbitmq_base import BaseRabbitMQConsumer, BaseRabbitMQProducer
from app.config import EmbeddingConfig


class RabbitMQConsumerImpl(BaseRabbitMQConsumer):
    def __init__(self, config: EmbeddingConfig) -> None:
        super().__init__(config)


class RabbitMQProducerImpl(BaseRabbitMQProducer):
    def __init__(self, config: EmbeddingConfig) -> None:
        super().__init__(config)
