"""RabbitMQ implementations for the llm_agent service."""
from dataclasses import dataclass

from shared.rabbitmq_base import BaseRabbitMQConsumer, BaseRabbitMQProducer
from app.core.config import Settings


@dataclass
class _QueueConfig:
    """Minimal config object for a single named queue."""
    rabbitmq_url: str
    rabbitmq_exchange: str
    rabbitmq_queue: str
    rabbitmq_prefetch_count: int


def make_consumer(settings: Settings, queue_name: str) -> BaseRabbitMQConsumer:
    """Create a consumer for a specific queue, sharing the exchange config."""
    cfg = _QueueConfig(
        rabbitmq_url=settings.rabbitmq_url,
        rabbitmq_exchange=settings.rabbitmq_exchange,
        rabbitmq_queue=queue_name,
        rabbitmq_prefetch_count=settings.rabbitmq_prefetch_count,
    )
    return BaseRabbitMQConsumer(cfg)


class RabbitMQProducerImpl(BaseRabbitMQProducer):
    """RabbitMQ producer for llm_agent."""

    def __init__(self, config: Settings) -> None:
        super().__init__(config)
