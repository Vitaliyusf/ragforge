"""MongoDB database session management."""
import time
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

from app.core.config import settings
from app.core.errors import DatabaseError


_client: Optional[MongoClient] = None
_db: Optional[Database] = None


def get_client() -> MongoClient:
    """Get or create MongoDB client with retry logic."""
    global _client
    
    if _client is not None:
        return _client
    
    for attempt in range(settings.mongodb_max_retries):
        try:
            _client = MongoClient(settings.mongodb_url)
            _client.admin.command('ping')
            return _client
        except Exception as e:
            if attempt < settings.mongodb_max_retries - 1:
                time.sleep(settings.mongodb_retry_delay)
            else:
                raise DatabaseError(f"Failed to initialize MongoDB after {settings.mongodb_max_retries} attempts: {e}")
    
    raise DatabaseError("Failed to initialize MongoDB client")


def get_db() -> Database:
    """Get MongoDB database instance."""
    global _db
    
    if _db is not None:
        return _db
    
    client = get_client()
    _db = client[settings.mongodb_database]
    return _db


def get_chats_collection() -> Collection:
    """Get chats collection."""
    db = get_db()
    return db["chats"]


def get_messages_collection() -> Collection:
    """Get messages collection."""
    db = get_db()
    return db["messages"]


def get_episodic_memories_collection() -> Collection:
    """Get episodic memories collection."""
    db = get_db()
    return db["episodic_memories"]


def get_semantic_preferences_collection() -> Collection:
    """Get semantic preferences collection."""
    db = get_db()
    return db["semantic_preferences"]


def get_memory_write_log_collection() -> Collection:
    """Get memory write log collection."""
    db = get_db()
    return db["memory_write_log"]


def ensure_tenant_indexes() -> None:
    """Create compound indexes that make tenant/user boundaries efficient and unique."""
    get_chats_collection().create_index(
        [("tenant_id", 1), ("owner_user_id", 1), ("id", 1)],
        unique=True,
        name="uniq_tenant_user_chat",
    )
    get_chats_collection().create_index(
        [("tenant_id", 1), ("owner_user_id", 1), ("updated_at", -1)],
        name="tenant_user_recent_chats",
    )
    get_messages_collection().create_index(
        [("tenant_id", 1), ("owner_user_id", 1), ("id", 1)],
        unique=True,
        name="uniq_tenant_user_message",
    )
    get_messages_collection().create_index(
        [("tenant_id", 1), ("owner_user_id", 1), ("chat_id", 1), ("timestamp", 1)],
        name="tenant_user_chat_messages",
    )
