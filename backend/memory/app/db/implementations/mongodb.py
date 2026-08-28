"""MongoDB database implementation."""
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from pymongo import MongoClient

from app.db.interfaces import IChatRepository, IMessageRepository, ILongTermMemoryRepository
from app.config import MemoryConfig
from app.core.errors import raise_database_failure
from app.services.tenant_scope import ownership_fields, scope_filter

logger = logging.getLogger(__name__)


class MongoDBChatRepository(IChatRepository):
    """MongoDB implementation of chat repository."""
    
    def __init__(self, config: MemoryConfig):
        """Initialize MongoDB chat repository."""
        self.config = config
        self._client: Optional[MongoClient] = None
        self._db = None
        self._collection = None
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize MongoDB connection with retry logic."""
        for attempt in range(self.config.mongodb_max_retries):
            try:
                self._client = MongoClient(self.config.mongodb_url)
                # Test connection
                self._client.admin.command('ping')
                self._db = self._client[self.config.mongodb_database]
                self._collection = self._db["chats"]
                logger.info("MongoDB initialized successfully on attempt %d", attempt + 1)
                return
            except Exception as e:
                if attempt < self.config.mongodb_max_retries - 1:
                    logger.warning("MongoDB initialization failed (attempt %d/%d): %s. Retrying...", attempt + 1, self.config.mongodb_max_retries, e)
                    time.sleep(self.config.mongodb_retry_delay)
                else:
                    logger.error("Failed to initialize MongoDB after %d attempts: %s", self.config.mongodb_max_retries, e)
                    raise_database_failure("initialize_chat_repository", e)

    def create(self, chat_id: str, title: str) -> bool:
        """Create a new chat."""
        if self._collection is None:
            raise_database_failure("create_chat", RuntimeError("chat collection unavailable"))
        
        try:
            now = datetime.now().isoformat()
            chat_doc = {
                "id": chat_id,
                "title": title,
                "created_at": now,
                "updated_at": now,
                **ownership_fields(),
            }
            self._collection.insert_one(chat_doc)
            return True
        except Exception as exc:
            raise_database_failure("create_chat", exc)
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all chats."""
        if self._collection is None:
            raise_database_failure("get_all_chats", RuntimeError("chat collection unavailable"))
        
        try:
            chats = list(self._collection.find(scope_filter(), {"_id": 0}).sort("updated_at", -1))
            return chats
        except Exception as exc:
            raise_database_failure("get_all_chats", exc)
    
    def delete(self, chat_id: str) -> bool:
        """Delete a chat."""
        if self._collection is None:
            raise_database_failure("delete_chat", RuntimeError("chat collection unavailable"))
        
        try:
            result = self._collection.delete_one(scope_filter({"id": chat_id}))
            return result.deleted_count > 0
        except Exception as exc:
            raise_database_failure("delete_chat", exc)
    
    def update_timestamp(self, chat_id: str, timestamp: str) -> bool:
        """Update chat's updated_at timestamp."""
        if self._collection is None:
            raise_database_failure("update_chat_timestamp", RuntimeError("chat collection unavailable"))
        
        try:
            result = self._collection.update_one(
                scope_filter({"id": chat_id}),
                {"$set": {"updated_at": timestamp}}
            )
            return result.modified_count > 0
        except Exception as exc:
            raise_database_failure("update_chat_timestamp", exc)
    
    def update_title(self, chat_id: str, title: str) -> bool:
        """Update chat's title."""
        if self._collection is None:
            raise_database_failure("update_chat_title", RuntimeError("chat collection unavailable"))
        
        try:
            now = datetime.now().isoformat()
            result = self._collection.update_one(
                scope_filter({"id": chat_id}),
                {"$set": {"title": title, "updated_at": now}}
            )
            return result.modified_count > 0
        except Exception as exc:
            raise_database_failure("update_chat_title", exc)


class MongoDBMessageRepository(IMessageRepository):
    """MongoDB implementation of message repository."""
    
    def __init__(self, config: MemoryConfig):
        """Initialize MongoDB message repository."""
        self.config = config
        self._client: Optional[MongoClient] = None
        self._db = None
        self._collection = None
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize MongoDB connection with retry logic."""
        for attempt in range(self.config.mongodb_max_retries):
            try:
                self._client = MongoClient(self.config.mongodb_url)
                # Test connection
                self._client.admin.command('ping')
                self._db = self._client[self.config.mongodb_database]
                self._collection = self._db["messages"]
                logger.info("MongoDB messages initialized successfully on attempt %d", attempt + 1)
                return
            except Exception as e:
                if attempt < self.config.mongodb_max_retries - 1:
                    logger.warning("MongoDB initialization failed (attempt %d/%d): %s. Retrying...", attempt + 1, self.config.mongodb_max_retries, e)
                    time.sleep(self.config.mongodb_retry_delay)
                else:
                    logger.error("Failed to initialize MongoDB after %d attempts: %s", self.config.mongodb_max_retries, e)
                    raise_database_failure("initialize_message_repository", e)

    def create(self, message_id: str, chat_id: str, sender: str, message: str, timestamp: str) -> bool:
        """Create a new message."""
        if self._collection is None:
            raise_database_failure("create_message", RuntimeError("message collection unavailable"))
        
        try:
            message_doc = {
                "id": message_id,
                "chat_id": chat_id,
                "sender": sender,
                "message": message,
                "timestamp": timestamp,
                **ownership_fields(),
            }
            self._collection.insert_one(message_doc)
            return True
        except Exception as exc:
            raise_database_failure("create_message", exc)
    
    def get_by_chat_id(self, chat_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a chat."""
        if self._collection is None:
            raise_database_failure("get_messages", RuntimeError("message collection unavailable"))
        
        try:
            messages = list(self._collection.find(
                scope_filter({"chat_id": chat_id}),
                {"_id": 0}
            ).sort("timestamp", 1))
            return messages
        except Exception as exc:
            raise_database_failure("get_messages", exc)
    
    def delete_by_chat_id(self, chat_id: str) -> bool:
        """Delete all messages for a chat."""
        if self._collection is None:
            raise_database_failure("delete_messages", RuntimeError("message collection unavailable"))
        
        try:
            result = self._collection.delete_many(scope_filter({"chat_id": chat_id}))
            return result.deleted_count > 0
        except Exception as exc:
            raise_database_failure("delete_messages", exc)


class MongoDBLongTermMemoryRepository(ILongTermMemoryRepository):
    """MongoDB implementation of long-term memory repository."""
    
    def __init__(self, config: MemoryConfig):
        """Initialize MongoDB long-term memory repository."""
        self.config = config
        self._client: Optional[MongoClient] = None
        self._db = None
        self._collection = None
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize MongoDB connection with retry logic."""
        for attempt in range(self.config.mongodb_max_retries):
            try:
                self._client = MongoClient(self.config.mongodb_url)
                # Test connection
                self._client.admin.command('ping')
                self._db = self._client[self.config.mongodb_database]
                self._collection = self._db["long_term_memory"]
                logger.info("MongoDB long-term memory initialized successfully on attempt %d", attempt + 1)
                return
            except Exception as e:
                if attempt < self.config.mongodb_max_retries - 1:
                    logger.warning("MongoDB initialization failed (attempt %d/%d): %s. Retrying...", attempt + 1, self.config.mongodb_max_retries, e)
                    time.sleep(self.config.mongodb_retry_delay)
                else:
                    logger.error("Failed to initialize MongoDB after %d attempts: %s", self.config.mongodb_max_retries, e)
                    raise
    
    def create(self, memory_id: str, content: str, category: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Create a new long-term memory entry."""
        if self._collection is None:
            return False
        
        try:
            now = datetime.now().isoformat()
            memory_doc = {
                "id": memory_id,
                "content": content,
                "category": category,
                "metadata": metadata or {},
                "created_at": now,
                "updated_at": now,
                **ownership_fields(),
            }
            self._collection.insert_one(memory_doc)
            return True
        except Exception:
            return False
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all long-term memory entries."""
        if self._collection is None:
            return []
        
        try:
            memories = list(self._collection.find(scope_filter(), {"_id": 0}).sort("created_at", -1))
            return memories
        except Exception:
            return []
    
    def get_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a long-term memory entry by ID."""
        if self._collection is None:
            return None
        
        try:
            memory = self._collection.find_one(scope_filter({"id": memory_id}), {"_id": 0})
            return memory
        except Exception:
            return None
    
    def update(self, memory_id: str, content: Optional[str] = None, category: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update a long-term memory entry."""
        if self._collection is None:
            return False
        
        try:
            now = datetime.now().isoformat()
            update_data = {"updated_at": now}
            
            if content is not None:
                update_data["content"] = content
            if category is not None:
                update_data["category"] = category
            if metadata is not None:
                update_data["metadata"] = metadata
            
            result = self._collection.update_one(
                scope_filter({"id": memory_id}),
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception:
            return False
    
    def delete(self, memory_id: str) -> bool:
        """Delete a long-term memory entry."""
        if self._collection is None:
            return False
        
        try:
            result = self._collection.delete_one(scope_filter({"id": memory_id}))
            return result.deleted_count > 0
        except Exception:
            return False
