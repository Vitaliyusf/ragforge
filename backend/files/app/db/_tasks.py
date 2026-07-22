"""File tasks collection repository mixin.

Operates on ``self.file_tasks_collection``.
Assumes ``BaseRepository`` is earlier in the MRO.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pymongo import DESCENDING

from app.core.errors import DatabaseException
from app.db._base import serialize
from app.utils.common import utcnow


class TasksRepositoryMixin:
    """CRUD operations on the ``file_tasks`` collection."""

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_task(self, task_doc: Dict[str, Any], *, session=None) -> bool:
        """Insert a new file task document."""
        col = self._require_collection(self.file_tasks_collection, "file_tasks")
        try:
            col.insert_one(self._scope_document(task_doc), **self._mongo_kwargs(session))
            return True
        except Exception as exc:
            raise DatabaseException(f"Failed to create file task: {exc}") from exc

    def update_task(self, task_id: str, updates: Dict[str, Any], *, session=None) -> bool:
        """Apply a partial ``$set`` update and stamp ``updated_at``."""
        col = self._require_collection(self.file_tasks_collection, "file_tasks")
        try:
            update_doc = self._update_document(
                {"$set": {"updated_at": utcnow()}},
                updates=updates,
            )
            result = col.update_one(
                self._scope_filter({"task_id": task_id}), update_doc, **self._mongo_kwargs(session)
            )
            return result.matched_count > 0
        except Exception as exc:
            raise DatabaseException(f"Failed to update task: {exc}") from exc

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_task_by_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return a serialized task document by ``task_id``."""
        col = self._require_collection(self.file_tasks_collection, "file_tasks")
        try:
            task = col.find_one(self._scope_filter({"task_id": task_id}), {"_id": 0})
            return serialize(task) if task else None
        except Exception as exc:
            raise DatabaseException(f"Failed to get file task: {exc}") from exc

    def get_raw_task_by_id(self, task_id: str, *, session=None) -> Optional[Dict[str, Any]]:
        """Return a raw (unserialized) task document by ``task_id``."""
        col = self._require_collection(self.file_tasks_collection, "file_tasks")
        try:
            return col.find_one(self._scope_filter({"task_id": task_id}), **self._mongo_kwargs(session))
        except Exception as exc:
            raise DatabaseException(f"Failed to get file task: {exc}") from exc

    def get_latest_task_for_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recently created task for a file."""
        col = self._require_collection(self.file_tasks_collection, "file_tasks")
        try:
            task = col.find_one(
                self._scope_filter({"file_id": file_id}),
                {"_id": 0},
                sort=[("created_at", DESCENDING)],
            )
            return serialize(task) if task else None
        except Exception as exc:
            raise DatabaseException(f"Failed to get latest task: {exc}") from exc

    # ------------------------------------------------------------------
    # Index bootstrap
    # ------------------------------------------------------------------

    def _ensure_tasks_indexes(self) -> None:
        if self.file_tasks_collection is None:
            return
        self.file_tasks_collection.create_index([("tenant_id", 1), ("task_id", 1)], unique=True, name="uniq_tenant_task")
        self.file_tasks_collection.create_index([("tenant_id", 1), ("file_id", 1)], name="tenant_file_tasks")
        self.file_tasks_collection.create_index([("tenant_id", 1), ("status", 1)], name="tenant_task_status")
        self.file_tasks_collection.create_index([("tenant_id", 1), ("checkpoint_id", 1)], name="tenant_checkpoint")
