"""Base classes for embedding service handlers."""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseService(ABC):
    """Minimal base holding logger and config."""

    def __init__(self, logger, config) -> None:
        self.logger = logger
        self.config = config


class BaseKafkaHandlerService(BaseService):
    """Base for Kafka consumer handlers that own a producer."""

    def __init__(self, producer, logger, config) -> None:
        super().__init__(logger, config)
        self.producer = producer

    @abstractmethod
    def process_request(self, request: Dict[str, Any]) -> None:
        """Handle one inbound Kafka message."""
