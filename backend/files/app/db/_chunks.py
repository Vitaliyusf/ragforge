"""File chunks collection repository mixin.

Operates on ``self.file_chunks_collection``.
Assumes ``BaseRepository`` is earlier in the MRO.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from pymongo import ASCENDING, DESCENDING

from shared.errors import DatabaseException


class ChunksRepositoryMixin:
    """Write and version operations on the ``file_chunks`` collection."""

    def create_chunks(
        self, chunk_docs: Iterable[Dict[str, Any]], *, session=None
    ) -> int:
        """Bulk-insert chunk documents. Returns the number of inserted chunks."""
        col = self._require_collection(self.file_chunks_collection, "file_chunks")
        docs = [self._scope_document(document) for document in chunk_docs]
        if not docs:
            return 0
        try:
            result = col.insert_many(docs, ordered=True, **self._mongo_kwargs(session))
            return len(result.inserted_ids)
        except Exception as exc:
            raise DatabaseException(f"Failed to create chunks: {exc}") from exc

    def delete_chunks_for_file(self, file_id: str, *, session=None) -> int:
        """Delete all chunks for a file. Returns the number of deleted chunks."""
        col = self._require_collection(self.file_chunks_collection, "file_chunks")
        try:
            result = col.delete_many(
                self._scope_filter({"file_id": file_id}), **self._mongo_kwargs(session)
            )
            return result.deleted_count
        except Exception as exc:
            raise DatabaseException(f"Failed to delete chunks: {exc}") from exc

    def get_next_chunk_version(self, document_id: str) -> int:
        """Return the next chunk version number for a document (1-based)."""
        col = self._require_collection(self.file_chunks_collection, "file_chunks")
        try:
            latest = col.find_one(
                self._scope_filter({"document_id": document_id}),
                {"chunk_version": 1},
                sort=[("chunk_version", DESCENDING)],
            )
        except Exception as exc:
            raise DatabaseException(f"Failed to get next chunk version: {exc}") from exc
        return 1 if latest is None else int(latest.get("chunk_version", 0)) + 1

    def get_eval_chunk_records(self, file_ids: List[str]) -> List[Dict[str, Any]]:
        """Return matchable chunk fields for tenant-wide golden-set preparation."""
        if not file_ids:
            return []
        col = self._require_collection(self.file_chunks_collection, "file_chunks")
        try:
            return list(
                col.find(
                    self._scope_filter(
                        {"file_id": {"$in": list(dict.fromkeys(file_ids))}},
                        owner_scope=False,
                    ),
                    {
                        "_id": 0,
                        "chunk_id": 1,
                        "file_id": 1,
                        "chunk_version": 1,
                        "text": 1,
                        "retrieval_allowed": 1,
                        "review_status": 1,
                    },
                )
            )
        except Exception as exc:
            raise DatabaseException(f"Failed to get eval chunks: {exc}") from exc

    # ------------------------------------------------------------------
    # Index bootstrap
    # ------------------------------------------------------------------

    def _ensure_chunks_indexes(self) -> None:
        if self.file_chunks_collection is None:
            return
        self.file_chunks_collection.create_index([("tenant_id", ASCENDING), ("chunk_id", ASCENDING)], unique=True, name="uniq_tenant_chunk")
        self.file_chunks_collection.create_index(
            [("tenant_id", ASCENDING), ("file_id", ASCENDING), ("chunk_index", ASCENDING)]
        )
        self.file_chunks_collection.create_index(
            [("tenant_id", ASCENDING), ("document_id", ASCENDING), ("chunk_version", ASCENDING)]
        )
        self.file_chunks_collection.create_index([("tenant_id", ASCENDING), ("review_status", ASCENDING)])
        self.file_chunks_collection.create_index([("tenant_id", ASCENDING), ("retrieval_allowed", ASCENDING)])
