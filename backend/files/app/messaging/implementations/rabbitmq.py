"""RabbitMQ consumer and producer implementations for the files service."""
from shared.rabbitmq_base import BaseRabbitMQConsumer, BaseRabbitMQProducer
from app.core.config import Settings


class RabbitMQConsumerImpl(BaseRabbitMQConsumer):
    """RabbitMQ consumer for the files service request queue."""

    def __init__(self, config: Settings) -> None:
        super().__init__(config)


class RabbitMQProducerImpl(BaseRabbitMQProducer):
    """RabbitMQ producer for the files service."""

    def __init__(self, config: Settings) -> None:
        super().__init__(config)
