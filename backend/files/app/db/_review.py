"""Review cases and decisions collection repository mixin.

Operates on ``self.file_review_cases_collection`` and
``self.file_review_decisions_collection``.
Assumes ``BaseRepository`` is earlier in the MRO.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pymongo import ASCENDING, DESCENDING

from shared.errors import DatabaseException
from app.db._base import serialize


class ReviewRepositoryMixin:
    """CRUD operations on the ``file_review_cases`` and ``file_review_decisions`` collections."""

    # ------------------------------------------------------------------
    # Review cases — write
    # ------------------------------------------------------------------

    def create_review_case(self, review_case_doc: Dict[str, Any], *, session=None) -> bool:
        """Insert a new review case document."""
        col = self._require_collection(
            self.file_review_cases_collection, "file_review_cases"
        )
        try:
            col.insert_one(self._scope_document(review_case_doc), **self._mongo_kwargs(session))
            return True
        except Exception as exc:
            raise DatabaseException(f"Failed to create review case: {exc}") from exc

    def update_review_case(
        self, review_case_id: str, updates: Dict[str, Any], *, session=None
    ) -> bool:
        """Apply a ``$set`` update to a review case."""
        col = self._require_collection(
            self.file_review_cases_collection, "file_review_cases"
        )
        try:
            result = col.update_one(
                self._scope_filter({"review_case_id": review_case_id}),
                {"$set": updates},
                **self._mongo_kwargs(session),
            )
            return result.matched_count > 0
        except Exception as exc:
            raise DatabaseException(f"Failed to update review case: {exc}") from exc

    def claim_review_case(
        self,
        review_case_id: str,
        *,
        extracted_text_hash: str,
        resume_token_hash: str,
        claim_id: str,
        claimed_at,
        session=None,
    ) -> bool:
        """Atomically reserve one pending case for exactly one decision flow."""
        col = self._require_collection(
            self.file_review_cases_collection, "file_review_cases"
        )
        try:
            result = col.update_one(
                self._scope_filter({
                    "review_case_id": review_case_id,
                    "status": "open",
                    "decision_status": "pending",
                    "extracted_text_hash": extracted_text_hash,
                    "graph_interrupt.resume_token_hash": resume_token_hash,
                }),
                {"$set": {
                    "status": "resolving",
                    "decision_status": "resolving",
                    "resolution_claim_id": claim_id,
                    "resolution_claimed_at": claimed_at,
                }},
                **self._mongo_kwargs(session),
            )
            return result.modified_count == 1
        except Exception as exc:
            raise DatabaseException(f"Failed to claim review case: {exc}") from exc

    # ------------------------------------------------------------------
    # Review cases — read
    # ------------------------------------------------------------------

    def get_review_case_by_id(self, review_case_id: str) -> Optional[Dict[str, Any]]:
        """Return a serialized review case by ``review_case_id``."""
        col = self._require_collection(
            self.file_review_cases_collection, "file_review_cases"
        )
        try:
            doc = col.find_one(self._scope_filter({"review_case_id": review_case_id}), {"_id": 0})
            return serialize(doc) if doc else None
        except Exception as exc:
            raise DatabaseException(f"Failed to get review case: {exc}") from exc

    def get_raw_review_case_by_id(
        self, review_case_id: str, *, session=None
    ) -> Optional[Dict[str, Any]]:
        """Return a raw (unserialized) review case by ``review_case_id``."""
        col = self._require_collection(
            self.file_review_cases_collection, "file_review_cases"
        )
        try:
            return col.find_one(
                self._scope_filter({"review_case_id": review_case_id}), **self._mongo_kwargs(session)
            )
        except Exception as exc:
            raise DatabaseException(f"Failed to get review case: {exc}") from exc

    def get_open_review_case_for_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Return the active (open) review case for a file."""
        col = self._require_collection(
            self.file_review_cases_collection, "file_review_cases"
        )
        try:
            doc = col.find_one(
                self._scope_filter({"file_id": file_id, "status": "open"}),
                {"_id": 0},
                sort=[("opened_at", DESCENDING)],
            )
            return serialize(doc) if doc else None
        except Exception as exc:
            raise DatabaseException(f"Failed to get open review case: {exc}") from exc

    # ------------------------------------------------------------------
    # Review decisions — write
    # ------------------------------------------------------------------

    def create_review_decision(
        self, decision_doc: Dict[str, Any], *, session=None
    ) -> bool:
        """Insert a new review decision document."""
        col = self._require_collection(
            self.file_review_decisions_collection, "file_review_decisions"
        )
        try:
            col.insert_one(self._scope_document(decision_doc), **self._mongo_kwargs(session))
            return True
        except Exception as exc:
            raise DatabaseException(f"Failed to create review decision: {exc}") from exc

    # ------------------------------------------------------------------
    # Review decisions — read
    # ------------------------------------------------------------------

    def get_latest_review_decision(
        self, review_case_id: str
    ) -> Optional[Dict[str, Any]]:
        """Return the most recent decision for a review case."""
        col = self._require_collection(
            self.file_review_decisions_collection, "file_review_decisions"
        )
        try:
            doc = col.find_one(
                self._scope_filter({"review_case_id": review_case_id}),
                {"_id": 0},
                sort=[("created_at", DESCENDING)],
            )
            return serialize(doc) if doc else None
        except Exception as exc:
            raise DatabaseException(f"Failed to get review decision: {exc}") from exc

    # ------------------------------------------------------------------
    # Index bootstrap
    # ------------------------------------------------------------------

    def _ensure_review_indexes(self) -> None:
        if self.file_review_cases_collection is not None:
            self.file_review_cases_collection.create_index(
                [("tenant_id", ASCENDING), ("review_case_id", ASCENDING)], unique=True, name="uniq_tenant_review_case"
            )
            self.file_review_cases_collection.create_index(
                [("tenant_id", ASCENDING), ("file_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"status": "open", "tenant_id": {"$exists": True}},
                name="uniq_open_case_per_tenant_file",
            )
        if self.file_review_decisions_collection is not None:
            self.file_review_decisions_collection.create_index(
                [("tenant_id", ASCENDING), ("review_case_id", ASCENDING)],
                unique=True,
                name="uniq_tenant_review_decision",
            )
            self.file_review_decisions_collection.create_index([("tenant_id", ASCENDING), ("file_id", ASCENDING)])
