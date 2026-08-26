"""Files collection repository mixin.

Operates exclusively on ``self.collection`` (the ``files`` collection).
Assumes ``BaseRepository`` is earlier in the MRO.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pymongo import DESCENDING

from app.core.errors import DatabaseException
from app.db._base import serialize
from app.utils.common import utcnow


class FilesRepositoryMixin:
    """CRUD and update operations on the primary ``files`` collection."""

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create(self, file_doc: Dict[str, Any], *, session=None) -> bool:
        """Insert a new file document."""
        try:
            self.collection.insert_one(self._scope_document(file_doc), **self._mongo_kwargs(session))
            return True
        except Exception as exc:
            raise DatabaseException(f"Failed to create file: {exc}") from exc

    def update_file(self, file_id: str, updates: Dict[str, Any], *, session=None) -> bool:
        """Apply a partial ``$set`` update and stamp ``updated_at``."""
        try:
            update_doc = self._update_document(
                {"$set": {"updated_at": utcnow()}},
                updates=updates,
            )
            result = self.collection.update_one(
                self._scope_filter({"file_id": file_id}), update_doc, **self._mongo_kwargs(session)
            )
            return result.matched_count > 0
        except Exception as exc:
            raise DatabaseException(f"Failed to update file: {exc}") from exc

    def update_stage(self, file_id: str, stage_name: str, status: str, *, session=None) -> bool:
        """Update a single stage entry and stamp ``updated_at``."""
        try:
            result = self.collection.update_one(
                self._scope_filter({"file_id": file_id}),
                {"$set": {f"stage.{stage_name}": status, "updated_at": utcnow()}},
                **self._mongo_kwargs(session),
            )
            return result.matched_count > 0
        except Exception as exc:
            raise DatabaseException(f"Failed to update stage: {exc}") from exc

    def update_status(self, file_id: str, status: str, *, session=None) -> bool:
        """Update the file lifecycle status."""
        return self.update_file(file_id, {"status": status}, session=session)

    def update_review_status(self, file_id: str, review_status: str, *, session=None) -> bool:
        """Update the file review status."""
        return self.update_file(file_id, {"review_status": review_status}, session=session)

    def update_summary(self, file_id: str, summary: str, *, session=None) -> bool:
        """Persist a generated summary and mark the summary stage done."""
        return self.update_file(
            file_id,
            {"summary": summary, "stage.summary": "done"},
            session=session,
        )

    def update_metadata(self, file_id: str, keywords: List[str], *, session=None) -> bool:
        """Persist extracted keywords and mark the metadata stage done."""
        return self.update_file(
            file_id,
            {"metadata.keywords": keywords, "stage.metadata": "done"},
            session=session,
        )

    def update_suggested_questions(
        self, file_id: str, questions: List[str], *, session=None
    ) -> bool:
        """Persist suggested questions for a file."""
        return self.update_file(file_id, {"suggested_questions": questions}, session=session)

    def delete(self, file_id: str, *, session=None) -> bool:
        """Delete a file document."""
        try:
            result = self.collection.delete_one(
                self._scope_filter({"file_id": file_id}), **self._mongo_kwargs(session)
            )
            return result.deleted_count > 0
        except Exception as exc:
            raise DatabaseException(f"Failed to delete file: {exc}") from exc

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_all(self) -> List[Dict[str, Any]]:
        """Return all file documents sorted by most recent first."""
        try:
            files = list(
                self.collection.find(self._scope_filter(), {"_id": 0}).sort("created_at", DESCENDING)
            )
            return [serialize(f) for f in files]
        except Exception as exc:
            raise DatabaseException(f"Failed to get files: {exc}") from exc

    def get_filename_records(self) -> List[Dict[str, str]]:
        """Return only ids and filenames visible in the trusted caller scope."""
        try:
            files = self.collection.find(
                # Golden sets are tenant-wide and admin-only. User-owned file
                # records must therefore be visible across the tenant, while
                # the mandatory tenant predicate remains fail-closed.
                self._scope_filter(owner_scope=False),
                {"_id": 0, "file_id": 1, "filename": 1},
            )
            return [serialize(file_doc) for file_doc in files]
        except Exception as exc:
            raise DatabaseException(f"Failed to get file labels: {exc}") from exc

    def get_eval_file_records(self, file_ids: List[str]) -> List[Dict[str, Any]]:
        """Return readiness fields for golden-set files in the caller's tenant.

        Evaluation datasets are tenant-wide and admin-only, so owner scoping is
        deliberately disabled while the mandatory tenant predicate remains.
        """
        if not file_ids:
            return []
        try:
            files = self.collection.find(
                self._scope_filter(
                    {"file_id": {"$in": list(dict.fromkeys(file_ids))}},
                    owner_scope=False,
                ),
                {
                    "_id": 0,
                    "file_id": 1,
                    "status": 1,
                    "review_status": 1,
                    "stage.embedding": 1,
                    "stage.vector": 1,
                },
            )
            return [serialize(file_doc) for file_doc in files]
        except Exception as exc:
            raise DatabaseException(f"Failed to get eval file readiness: {exc}") from exc

    def get_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Return a serialized file document by ``file_id``."""
        try:
            doc = self.collection.find_one(self._scope_filter({"file_id": file_id}), {"_id": 0})
            return serialize(doc) if doc is not None else None
        except Exception as exc:
            raise DatabaseException(f"Failed to get file: {exc}") from exc

    def get_raw_by_id(self, file_id: str, *, session=None) -> Optional[Dict[str, Any]]:
        """Return a raw (unserialized) file document by ``file_id``."""
        try:
            return self.collection.find_one(
                self._scope_filter({"file_id": file_id}), **self._mongo_kwargs(session)
            )
        except Exception as exc:
            raise DatabaseException(f"Failed to get file: {exc}") from exc

    def get_summary(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Return ``{summary, stage}`` for a file."""
        try:
            doc = self.collection.find_one(
                self._scope_filter({"file_id": file_id}),
                {"_id": 0, "summary": 1, "stage.summary": 1},
            )
            if not doc:
                return None
            return {
                "summary": doc.get("summary", ""),
                "stage": doc.get("stage", {}).get("summary", "waiting"),
            }
        except Exception as exc:
            raise DatabaseException(f"Failed to get summary: {exc}") from exc

    def get_suggested_questions_from_complete_files(self) -> List[str]:
        """Return deduplicated suggested questions from all complete files."""
        try:
            files = list(
                self.collection.find(
                    self._scope_filter({
                        "status": "complete",
                        "suggested_questions": {"$exists": True, "$ne": []},
                    }),
                    {"suggested_questions": 1},
                )
            )
            questions: List[str] = []
            seen: set = set()
            for file_doc in files:
                for question in file_doc.get("suggested_questions", []):
                    if question and question not in seen:
                        seen.add(question)
                        questions.append(question)
            return questions
        except Exception as exc:
            raise DatabaseException(f"Failed to get suggested questions: {exc}") from exc

    # ------------------------------------------------------------------
    # Index bootstrap
    # ------------------------------------------------------------------

    def _ensure_files_indexes(self) -> None:
        self.collection.create_index([("tenant_id", 1), ("file_id", 1)], unique=True, name="uniq_tenant_file")
        self.collection.create_index([("tenant_id", 1), ("owner_admin_id", 1), ("created_at", -1)], name="admin_files")
        self.collection.create_index([("tenant_id", 1), ("owner_user_id", 1), ("status", 1)], name="user_file_status")
        self.collection.create_index([("tenant_id", 1), ("review_status", 1)], name="tenant_review_status")
