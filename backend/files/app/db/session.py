"""MongoDB session management."""
import time
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.core.config import settings
from shared.errors import DatabaseException, ErrorCode


_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    """Return the MongoDB client singleton, creating it on first call.

    Raises:
        DatabaseException: If all connection attempts fail.
    """
    global _client

    if _client is not None:
        return _client

    last_exc: Optional[Exception] = None
    for attempt in range(settings.mongodb_max_retries):
        try:
            candidate = MongoClient(settings.mongodb_url)
            candidate.admin.command("ping")
            _client = candidate
            return _client
        except Exception as exc:
            last_exc = exc
            if attempt < settings.mongodb_max_retries - 1:
                time.sleep(settings.mongodb_retry_delay)

    raise DatabaseException(
        f"Failed to connect to MongoDB after {settings.mongodb_max_retries} attempts: {last_exc}",
        error_code=ErrorCode.DATABASE_CONNECTION_ERROR,
    )


def get_db() -> Database:
    """Return the files domain database."""
    return get_client()[settings.files_db_name]


def get_audit_db() -> Database:
    """Return the audit trail database."""
    return get_client()[settings.audit_db_name]


def get_files_collection() -> Collection:
    """Return the ``files`` collection."""
    return get_db()["files"]


def get_file_tasks_collection() -> Collection:
    """Return the ``file_tasks`` collection."""
    return get_db()["file_tasks"]


def get_file_chunks_collection() -> Collection:
    """Return the ``file_chunks`` collection."""
    return get_db()["file_chunks"]


def get_file_review_cases_collection() -> Collection:
    """Return the ``file_review_cases`` collection."""
    return get_db()["file_review_cases"]


def get_file_review_decisions_collection() -> Collection:
    """Return the ``file_review_decisions`` collection."""
    return get_db()["file_review_decisions"]


def get_file_audit_events_collection() -> Collection:
    """Return the ``file_audit_events`` collection."""
    return get_audit_db()["file_audit_events"]
