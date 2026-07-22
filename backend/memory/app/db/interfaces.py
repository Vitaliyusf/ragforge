"""Database repository interfaces."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class IChatRepository(ABC):
    """Interface for chat repository operations."""
    
    @abstractmethod
    def create(self, chat_id: str, title: str) -> bool:
        """Create a new chat."""
        pass
    
    @abstractmethod
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all chats."""
        pass
    
    @abstractmethod
    def delete(self, chat_id: str) -> bool:
        """Delete a chat."""
        pass
    
    @abstractmethod
    def update_timestamp(self, chat_id: str, timestamp: str) -> bool:
        """Update chat's updated_at timestamp."""
        pass
    
    @abstractmethod
    def update_title(self, chat_id: str, title: str) -> bool:
        """Update chat's title."""
        pass


class IMessageRepository(ABC):
    """Interface for message repository operations."""
    
    @abstractmethod
    def create(self, message_id: str, chat_id: str, sender: str, message: str, timestamp: str) -> bool:
        """Create a new message."""
        pass
    
    @abstractmethod
    def get_by_chat_id(self, chat_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a chat."""
        pass
    
    @abstractmethod
    def delete_by_chat_id(self, chat_id: str) -> bool:
        """Delete all messages for a chat."""
        pass


class ILongTermMemoryRepository(ABC):
    """Interface for long-term memory repository operations."""
    
    @abstractmethod
    def create(self, memory_id: str, content: str, category: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Create a new long-term memory entry."""
        pass
    
    @abstractmethod
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all long-term memory entries."""
        pass
    
    @abstractmethod
    def get_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a long-term memory entry by ID."""
        pass
    
    @abstractmethod
    def update(self, memory_id: str, content: Optional[str] = None, category: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update a long-term memory entry."""
        pass
    
    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """Delete a long-term memory entry."""
        pass