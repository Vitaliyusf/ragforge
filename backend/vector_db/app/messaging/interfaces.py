"""Message queue interfaces."""
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator


class IProducer(ABC):
    """Interface for message producers."""

    @abstractmethod
    def send(self, topic: str, message: Dict[str, Any]) -> None:
        """Send a message to a topic."""
        raise NotImplementedError

    @abstractmethod
    def flush(self) -> None:
        """Flush pending messages."""
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the producer is connected."""
        raise NotImplementedError


class IConsumer(ABC):
    """Interface for message consumers."""

    @abstractmethod
    def consume(self, timeout_ms: int = 1000) -> Iterator[Dict[str, Any]]:
        """Consume decoded messages with their source topic."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close the consumer."""
        raise NotImplementedError

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the consumer is connected."""
        raise NotImplementedError
