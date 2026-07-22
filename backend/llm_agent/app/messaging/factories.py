"""Factory for llm_agent message queue clients."""
from app.core.config import Settings
from app.messaging.implementations.rabbitmq import make_consumer, RabbitMQProducerImpl
from shared.rabbitmq_base import BaseRabbitMQConsumer


class MessageQueueFactory:
    @staticmethod
    def create_consumer(settings: Settings, queue_name: str) -> BaseRabbitMQConsumer:
        return make_consumer(settings, queue_name)

    @staticmethod
    def create_producer(settings: Settings) -> RabbitMQProducerImpl:
        return RabbitMQProducerImpl(settings)
