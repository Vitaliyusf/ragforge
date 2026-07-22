"""Factory for creating message queue clients."""
from typing import TYPE_CHECKING, Optional
from app.messaging.implementations.kafka import KafkaProducerImpl, KafkaConsumerImpl
from app.messaging.interfaces import IProducer, IConsumer
from app.config import EmbeddingConfig

if TYPE_CHECKING:
    from app.messaging.implementations.rabbitmq import RabbitMQConsumerImpl, RabbitMQProducerImpl


class MessageQueueFactory:
    """Factory for creating message queue clients."""
    
    @staticmethod
    def create_producer(config: EmbeddingConfig, implementation: str = "kafka") -> IProducer:
        """Create a message producer."""
        if implementation == "kafka":
            return KafkaProducerImpl(config)
        else:
            raise ValueError(f"Unknown producer implementation: {implementation}")
    
    @staticmethod
    def create_consumer(config: EmbeddingConfig, topic: str, implementation: str = "kafka", group_id: Optional[str] = None) -> IConsumer:
        """Create a message consumer."""
        if implementation == "kafka":
            return KafkaConsumerImpl(config, topic, group_id)
        else:
            raise ValueError(f"Unknown consumer implementation: {implementation}")

    @staticmethod
    def create_rabbitmq_consumer(config) -> "RabbitMQConsumerImpl":
        from app.messaging.implementations.rabbitmq import RabbitMQConsumerImpl
        return RabbitMQConsumerImpl(config)

    @staticmethod
    def create_rabbitmq_producer(config) -> "RabbitMQProducerImpl":
        from app.messaging.implementations.rabbitmq import RabbitMQProducerImpl
        return RabbitMQProducerImpl(config)
