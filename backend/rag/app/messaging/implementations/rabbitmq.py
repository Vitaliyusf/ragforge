"""RabbitMQ consumer and producer implementations for the RAG service."""
from shared.rabbitmq_base import BaseRabbitMQConsumer, BaseRabbitMQProducer
from app.core.config import Settings


class RabbitMQConsumerImpl(BaseRabbitMQConsumer):
    def __init__(self, config: Settings) -> None:
        super().__init__(config)


class RabbitMQProducerImpl(BaseRabbitMQProducer):
    def __init__(self, config: Settings) -> None:
        super().__init__(config)
