"""Database session management for MongoDB."""
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database

# Global MongoDB client (initialized on startup)
_mongo_client: Optional[MongoClient] = None
_mongo_db: Optional[Database] = None


def get_client() -> MongoClient:
    """Get MongoDB client instance."""
    if _mongo_client is None:
        raise RuntimeError("MongoDB client not initialized. Call init_db() first.")
    return _mongo_client


def get_db() -> Database:
    """Get MongoDB database instance."""
    if _mongo_db is None:
        raise RuntimeError("MongoDB database not initialized. Call init_db() first.")
    return _mongo_db


def init_db(connection_string: str, database_name: str) -> None:
    """Initialize MongoDB connection."""
    global _mongo_client, _mongo_db
    _mongo_client = MongoClient(connection_string, tz_aware=True)
    _mongo_db = _mongo_client[database_name]


def close_db() -> None:
    """Close MongoDB connection."""
    global _mongo_client, _mongo_db
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
        _mongo_db = None
