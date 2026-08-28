"""Audit events collection repository mixin.

Operates on ``self.file_audit_events_collection``.
Assumes ``BaseRepository`` is earlier in the MRO.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pymongo import ASCENDING, DESCENDING

from shared.errors import DatabaseException
from app.db._base import serialize


class AuditRepositoryMixin:
    """Write and cursor-paginated read operations on ``file_audit_events``."""

    def insert_audit_event(
        self, event_doc: Dict[str, Any], *, session=None
    ) -> bool:
        """Insert a single audit event document."""
        col = self._require_collection(
            self.file_audit_events_collection, "file_audit_events"
        )
        try:
            col.insert_one(self._scope_document(event_doc), **self._mongo_kwargs(session))
            return True
        except Exception as exc:
            raise DatabaseException(f"Failed to insert audit event: {exc}") from exc

    def get_audit_events(
        self,
        file_id: str,
        *,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Return up to ``limit`` audit events for ``file_id``, newest first.

        Uses keyset pagination via ``cursor`` (an ``event_id``). Returns
        ``(events, next_cursor)`` where ``next_cursor`` is ``None`` when
        the result set is exhausted.
        """
        col = self._require_collection(
            self.file_audit_events_collection, "file_audit_events"
        )
        try:
            query: Dict[str, Any] = {"file_id": file_id}
            if cursor:
                cursor_doc = col.find_one(self._scope_filter({"event_id": cursor}))
                if cursor_doc:
                    query["$or"] = [
                        {"created_at": {"$lt": cursor_doc["created_at"]}},
                        {
                            "created_at": cursor_doc["created_at"],
                            "event_id": {"$lt": cursor_doc["event_id"]},
                        },
                    ]
            events = list(
                col.find(self._scope_filter(query), {"_id": 0})
                .sort([("created_at", DESCENDING), ("event_id", DESCENDING)])
                .limit(limit)
            )
        except Exception as exc:
            raise DatabaseException(f"Failed to get audit events: {exc}") from exc

        serialized = [serialize(e) for e in events]
        next_cursor = serialized[-1]["event_id"] if len(serialized) == limit else None
        return serialized, next_cursor

    # ------------------------------------------------------------------
    # Index bootstrap
    # ------------------------------------------------------------------

    def _ensure_audit_indexes(self) -> None:
        if self.file_audit_events_collection is None:
            return
        self.file_audit_events_collection.create_index(
            [("tenant_id", ASCENDING), ("file_id", ASCENDING), ("created_at", DESCENDING)]
        )
        self.file_audit_events_collection.create_index([("tenant_id", ASCENDING), ("review_case_id", ASCENDING)])
        self.file_audit_events_collection.create_index([("tenant_id", ASCENDING), ("event_id", ASCENDING)], unique=True, name="uniq_tenant_event")
