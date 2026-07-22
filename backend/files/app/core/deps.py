"""Dependency-injection getters used by FastAPI route handlers.

All singletons are owned by ``app.main`` and exposed here via deferred
imports to avoid circular-import issues at startup.
"""
from app.db.repository import FileRepository
from app.db.session import get_files_collection
from pymongo.collection import Collection
from fastapi import Depends


def get_file_repository(
    collection: Collection = Depends(get_files_collection),
) -> FileRepository:
    """Return a ``FileRepository`` bound to the primary files collection."""
    return FileRepository(collection)
