"""Message queue interfaces."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Iterator, Optional


class IProducer(ABC):
    """Interface for message producers."""
    
    @abstractmethod
    def send(self, topic: str, message: Dict[str, Any], key: Optional[str] = None) -> None:
        """Send a message to a topic."""
        pass
    
    @abstractmethod
    def flush(self) -> None:
        """Flush pending messages."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if producer is connected."""
        pass


class IConsumer(ABC):
    """Interface for message consumers."""
    
    @abstractmethod
    def consume(self, timeout_ms: int = 1000) -> Iterator[Dict[str, Any]]:
        """Consume messages from the subscribed topic."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close the consumer."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if consumer is connected."""
        pass
