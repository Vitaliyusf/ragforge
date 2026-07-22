"""Factory for vector_db service message queue clients."""
from app.core.config import Settings
from app.messaging.implementations.rabbitmq import RabbitMQConsumerImpl, RabbitMQProducerImpl


class MessageQueueFactory:
    @staticmethod
    def create_consumer(config: Settings) -> RabbitMQConsumerImpl:
        return RabbitMQConsumerImpl(config)

    @staticmethod
    def create_producer(config: Settings) -> RabbitMQProducerImpl:
        return RabbitMQProducerImpl(config)
