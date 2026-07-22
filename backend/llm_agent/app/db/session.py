"""MongoDB session management."""
import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
import time

from app.core.config import get_settings

logger = logging.getLogger(__name__)


_client: Optional[MongoClient] = None
_db: Optional[Database] = None


def get_client() -> MongoClient:
    """
    Get or create MongoDB client with retry logic.
    
    Returns:
        MongoClient instance
        
    Raises:
        Exception: If connection fails after retries
    """
    global _client
    if _client is not None:
        return _client
    
    settings = get_settings()
    max_retries = 5
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            _client = MongoClient(
                settings.mongodb_url,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
            # Test connection
            _client.admin.command('ping')
            return _client
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "MongoDB connection failed (attempt %d/%d): %s. Retrying...",
                    attempt + 1, max_retries, e,
                )
                time.sleep(retry_delay)
            else:
                logger.error(
                    "Failed to connect to MongoDB after %d attempts: %s", max_retries, e
                )
                raise
    
    raise RuntimeError("MongoDB client not available")


def get_db() -> Database:
    """
    Get MongoDB database instance.
    
    Returns:
        Database instance
    """
    global _db
    if _db is not None:
        return _db
    
    settings = get_settings()
    client = get_client()
    _db = client[settings.mongodb_database]
    return _db


def get_users_collection() -> Collection:
    """
    Get users collection (placeholder for future use).
    
    Returns:
        Collection instance for users
    """
    db = get_db()
    return db["users"]
