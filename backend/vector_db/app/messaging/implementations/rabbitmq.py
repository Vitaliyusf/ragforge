"""RabbitMQ consumer and producer for the vector_db service."""
from shared.rabbitmq_base import BaseRabbitMQConsumer, BaseRabbitMQProducer
from app.core.config import Settings


class RabbitMQConsumerImpl(BaseRabbitMQConsumer):
    def __init__(self, config: Settings) -> None:
        super().__init__(config)


class RabbitMQProducerImpl(BaseRabbitMQProducer):
    def __init__(self, config: Settings) -> None:
        super().__init__(config)
