"""Message service for business logic."""
from typing import List, Dict, Any
from datetime import datetime
from pymongo.collection import Collection

from app.core.errors import ChatNotFoundError, raise_database_failure
from shared.logging import ServiceLogger
from app.db.session import get_messages_collection
from app.services.chat_service import ChatService
from app.services.tenant_scope import ownership_fields, scope_filter
from shared.chat_metadata import sanitize_chat_metadata


class MessageService:
    """Service for message operations."""
    
    def __init__(self, logger: ServiceLogger, chat_service: ChatService):
        """Initialize message service."""
        self.logger = logger
        self.chat_service = chat_service
    
    def _get_collection(self) -> Collection:
        """Get messages collection."""
        return get_messages_collection()
    
    def add_message(
        self, 
        message_id: str, 
        chat_id: str, 
        sender: str, 
        message: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Add a message to a chat."""
        try:
            # Ensure chat exists
            try:
                self.chat_service.get_chat(chat_id)
            except ChatNotFoundError:
                self.chat_service.create_chat(chat_id, "New Chat")
            
            collection = self._get_collection()
            timestamp = datetime.now().isoformat()
            
            message_doc = {
                "id": message_id,
                "chat_id": chat_id,
                "sender": sender,
                "message": message,
                "timestamp": timestamp,
                "metadata": sanitize_chat_metadata(metadata),
                **ownership_fields(),
            }
            collection.insert_one(message_doc)
            
            # Update chat timestamp
            self.chat_service.update_timestamp(chat_id, timestamp)
            
            self.logger.log("message_service:add", "Message added", {"message_id": message_id, "chat_id": chat_id})
            return message_doc
        except Exception as exc:
            self.logger.log("message_service:add", "Error adding message", {"message_id": message_id, "error": str(exc)}, "E")
            raise_database_failure("add_message", exc)
    
    def get_messages(self, chat_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a chat."""
        try:
            collection = self._get_collection()
            messages = list(collection.find(
                scope_filter({"chat_id": chat_id}), 
                {"_id": 0}
            ).sort("timestamp", 1))
            for message in messages:
                message.setdefault("metadata", {})
            
            self.logger.log("message_service:get", "Retrieved messages", {"chat_id": chat_id, "count": len(messages)})
            return messages
        except Exception as exc:
            self.logger.log("message_service:get", "Error retrieving messages", {"chat_id": chat_id, "error": str(exc)}, "E")
            raise_database_failure("get_messages", exc)
    
    def delete_messages_by_chat(self, chat_id: str) -> bool:
        """Delete all messages for a chat."""
        try:
            collection = self._get_collection()
            result = collection.delete_many(scope_filter({"chat_id": chat_id}))
            
            self.logger.log("message_service:delete", "Messages deleted", {"chat_id": chat_id, "count": result.deleted_count})
            return result.deleted_count > 0
        except Exception as exc:
            self.logger.log("message_service:delete", "Error deleting messages", {"chat_id": chat_id, "error": str(exc)}, "E")
            raise_database_failure("delete_messages", exc)
