"""Chat service for business logic."""
from typing import List, Dict, Any
from datetime import datetime
from pymongo.collection import Collection

from app.core.errors import ChatNotFoundError, DatabaseError
from app.core.logging_config import ServiceLogger
from app.db.session import get_chats_collection
from app.services.tenant_scope import ownership_fields, scope_filter


class ChatService:
    """Service for chat operations."""
    
    def __init__(self, logger: ServiceLogger):
        """Initialize chat service."""
        self.logger = logger
    
    def _get_collection(self) -> Collection:
        """Get chats collection."""
        return get_chats_collection()
    
    def create_chat(self, chat_id: str, title: str) -> Dict[str, Any]:
        """Create a new chat."""
        try:
            collection = self._get_collection()
            now = datetime.now().isoformat()
            
            # Check if chat already exists
            existing = collection.find_one(scope_filter({"id": chat_id}))
            if existing:
                self.logger.log("chat_service:create", "Chat already exists", {"chat_id": chat_id})
                return {"id": chat_id, "title": existing.get("title", title), "created_at": existing.get("created_at", now), "updated_at": now}
            
            chat_doc = {
                "id": chat_id,
                "title": title,
                "created_at": now,
                "updated_at": now
                , **ownership_fields()
            }
            collection.insert_one(chat_doc)
            
            self.logger.log("chat_service:create", "Chat created", {"chat_id": chat_id, "title": title})
            return chat_doc
        except Exception as e:
            self.logger.log("chat_service:create", "Error creating chat", {"chat_id": chat_id, "error": str(e)}, "E")
            raise DatabaseError(f"Failed to create chat: {e}")
    
    def get_all_chats(self) -> List[Dict[str, Any]]:
        """Get all chats."""
        try:
            collection = self._get_collection()
            chats = list(collection.find(scope_filter(), {"_id": 0}).sort("updated_at", -1))
            self.logger.log("chat_service:get_all", "Retrieved chats", {"count": len(chats)})
            return chats
        except Exception as e:
            self.logger.log("chat_service:get_all", "Error retrieving chats", {"error": str(e)}, "E")
            raise DatabaseError(f"Failed to retrieve chats: {e}")
    
    def get_chat(self, chat_id: str) -> Dict[str, Any]:
        """Get a chat by ID."""
        try:
            collection = self._get_collection()
            chat = collection.find_one(scope_filter({"id": chat_id}), {"_id": 0})
            if not chat:
                raise ChatNotFoundError(f"Chat {chat_id} not found")
            return chat
        except ChatNotFoundError:
            raise
        except Exception as e:
            self.logger.log("chat_service:get", "Error retrieving chat", {"chat_id": chat_id, "error": str(e)}, "E")
            raise DatabaseError(f"Failed to retrieve chat: {e}")
    
    def delete_chat(self, chat_id: str) -> bool:
        """Delete a chat."""
        try:
            collection = self._get_collection()
            result = collection.delete_one(scope_filter({"id": chat_id}))
            if result.deleted_count == 0:
                raise ChatNotFoundError(f"Chat {chat_id} not found")
            
            self.logger.log("chat_service:delete", "Chat deleted", {"chat_id": chat_id})
            return True
        except ChatNotFoundError:
            raise
        except Exception as e:
            self.logger.log("chat_service:delete", "Error deleting chat", {"chat_id": chat_id, "error": str(e)}, "E")
            raise DatabaseError(f"Failed to delete chat: {e}")
    
    def update_timestamp(self, chat_id: str, timestamp: str) -> bool:
        """Update chat's updated_at timestamp."""
        try:
            collection = self._get_collection()
            result = collection.update_one(
                scope_filter({"id": chat_id}),
                {"$set": {"updated_at": timestamp}}
            )
            return result.modified_count > 0
        except Exception as e:
            self.logger.log("chat_service:update_timestamp", "Error updating timestamp", {"chat_id": chat_id, "error": str(e)}, "E")
            return False
    
    def update_title(self, chat_id: str, title: str) -> bool:
        """Update chat's title."""
        try:
            collection = self._get_collection()
            now = datetime.now().isoformat()
            result = collection.update_one(
                scope_filter({"id": chat_id}),
                {"$set": {"title": title, "updated_at": now}}
            )
            if result.modified_count > 0:
                self.logger.log("chat_service:update_title", "Chat title updated", {"chat_id": chat_id, "title": title})
                return True
            return False
        except Exception as e:
            self.logger.log("chat_service:update_title", "Error updating title", {"chat_id": chat_id, "error": str(e)}, "E")
            return False

    def update_compressed_summary(self, chat_id: str, summary: str) -> bool:
        """Store a compressed summary of the chat's conversation history."""
        try:
            collection = self._get_collection()
            result = collection.update_one(
                scope_filter({"id": chat_id}),
                {"$set": {"compressed_summary": summary, "updated_at": datetime.now().isoformat()}}
            )
            if result.modified_count > 0:
                self.logger.log("chat_service:update_compressed_summary", "Summary stored", {"chat_id": chat_id})
            return result.modified_count > 0
        except Exception as e:
            self.logger.log("chat_service:update_compressed_summary", "Error", {"chat_id": chat_id, "error": str(e)}, "E")
            return False

    def get_compressed_summary(self, chat_id: str) -> str:
        """Return the stored compressed summary for a chat, or empty string."""
        try:
            collection = self._get_collection()
            chat = collection.find_one(scope_filter({"id": chat_id}), {"_id": 0, "compressed_summary": 1})
            return (chat or {}).get("compressed_summary", "") or ""
        except Exception:
            return ""
