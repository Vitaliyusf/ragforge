"""Qdrant-backed retrieval index for memory.

This module owns exactly one responsibility: moving points in and out of the
memory vector collection. It never produces a vector — every caller supplies
one from :mod:`app.services.memory_embedding_client` — and it never swallows a
failure into a success, because the canonical service above it has to record
reconciliation state when the index and MongoDB disagree.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from shared.logging import ServiceLogger
from app.services.tenant_scope import current_identity


class MemoryVectorIndexError(RuntimeError):
    """A memory vector index operation did not complete."""


class MemoryVectorIndex:
    """Small Qdrant client wrapper using the HTTP API."""

    def __init__(self, logger: ServiceLogger):
        self.logger = logger
        self._enabled = bool(settings.qdrant_enabled and settings.qdrant_url)
        self._collection_ready = False

    def is_enabled(self) -> bool:
        """Return whether the vector index is enabled."""
        return self._enabled

    @property
    def collection_name(self) -> str:
        """Return the active memory collection."""
        return settings.qdrant_collection_name

    @property
    def vector_size(self) -> int:
        """Return the dimensionality this collection is created for."""
        return settings.memory_embedding_dimensions

    def _collection_url(self) -> str:
        return f"{settings.qdrant_url.rstrip('/')}/collections/{self.collection_name}"

    def _request(self, method: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if settings.qdrant_api_key:
            headers["api-key"] = settings.qdrant_api_key

        with httpx.Client(timeout=settings.qdrant_timeout_seconds) as client:
            response = client.request(method, path, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
            return body if isinstance(body, dict) else {}

    def _ensure_collection(self) -> None:
        if self._collection_ready or not self._enabled:
            return
        try:
            self._request(
                "PUT",
                self._collection_url(),
                {
                    "vectors": {
                        "size": self.vector_size,
                        "distance": "Cosine",
                    }
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 409:
                self.logger.log(
                    "memory_vector_index:_ensure_collection",
                    "Failed to ensure memory vector collection",
                    {"error": str(exc), "collection": self.collection_name},
                    "W",
                )
                raise MemoryVectorIndexError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise MemoryVectorIndexError(str(exc)) from exc
        self._collection_ready = True

    def _require_identity(self, operation: str) -> Any:
        identity = current_identity()
        if identity is None:
            raise MemoryVectorIndexError(
                f"authenticated identity is required for memory vector {operation}"
            )
        return identity

    def point_id(self, tenant_id: str, user_id: str, memory_id: str) -> str:
        """Return the deterministic point id for one tenant-scoped memory."""
        return str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"memory:{tenant_id}:{user_id}:{memory_id}")
        )

    def upsert_memory(self, memory_doc: Dict[str, Any], vector: List[float]) -> str:
        """Upsert one memory point and return its point id."""
        if not self._enabled:
            raise MemoryVectorIndexError("memory vector index is disabled")
        if len(vector) != self.vector_size:
            raise MemoryVectorIndexError(
                f"vector dimensionality mismatch: expected {self.vector_size}, got {len(vector)}"
            )
        identity = self._require_identity("indexing")
        self._ensure_collection()
        payload = {
            "owner_id": memory_doc["owner_id"],
            "owner_type": memory_doc["owner_type"],
            "memory_id": memory_doc["id"],
            "memory_class": memory_doc["memory_class"],
            "text": memory_doc.get("content", {}).get("text", ""),
            "tags": memory_doc.get("tags", []),
            "importance": memory_doc.get("importance", 0.0),
            "updated_at": memory_doc.get("updated_at"),
            "status": memory_doc.get("status", "active"),
            # The revision the point was built from. Reconciliation compares it
            # to the canonical document to find vectors that describe wording
            # the memory no longer has.
            "revision": memory_doc.get("revision", 1),
            "valid_to": memory_doc.get("valid_to"),
            "archived": bool(memory_doc.get("archived_at")),
            "tenant_id": identity.tenant_id,
            "owner_user_id": identity.user_id,
            "owner_admin_id": identity.admin_id or identity.user_id,
        }
        point_id = self.point_id(identity.tenant_id, identity.user_id, memory_doc["id"])
        try:
            self._request(
                "PUT",
                f"{self._collection_url()}/points?wait=true",
                {"points": [{"id": point_id, "vector": vector, "payload": payload}]},
            )
        except httpx.HTTPError as exc:
            raise MemoryVectorIndexError(str(exc)) from exc
        return point_id

    def search(
        self,
        vector: List[float],
        owner_id: str,
        owner_type: str,
        limit: int,
        *,
        statuses: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search the memory collection for semantically similar memories."""
        if not self._enabled:
            raise MemoryVectorIndexError("memory vector index is disabled")
        if len(vector) != self.vector_size:
            raise MemoryVectorIndexError(
                f"vector dimensionality mismatch: expected {self.vector_size}, got {len(vector)}"
            )
        self._ensure_collection()
        identity = current_identity()
        must: List[Dict[str, Any]] = [
            {"key": "owner_id", "match": {"value": owner_id}},
            {"key": "owner_type", "match": {"value": owner_type}},
            {"key": "archived", "match": {"value": False}},
            {"key": "status", "match": {"any": list(statuses or ["active"])}},
        ]
        if identity is not None:
            must.extend([
                {"key": "tenant_id", "match": {"value": identity.tenant_id}},
                {"key": "owner_user_id", "match": {"value": identity.user_id}},
            ])
        try:
            response = self._request(
                "POST",
                f"{self._collection_url()}/points/search",
                {
                    "vector": vector,
                    "limit": limit,
                    "with_payload": True,
                    "filter": {"must": must},
                },
            )
        except httpx.HTTPError as exc:
            raise MemoryVectorIndexError(str(exc)) from exc
        results = response.get("result") or []
        return [
            {
                "memory_id": (item.get("payload") or {}).get("memory_id") or item.get("id"),
                "score": item.get("score", 0.0),
                "payload": item.get("payload") or {},
            }
            for item in results
        ]

    def scroll_points(
        self,
        limit: int,
        offset: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Page through the caller's own points, newest page cursor last.

        Reconciliation needs to see what the index actually holds in order to
        find points whose canonical memory is gone. The scroll is filtered to
        the caller's tenant and user like every other operation here, and it is
        bounded and resumable: it returns one page plus the cursor for the
        next, never the whole collection.
        """
        if not self._enabled:
            raise MemoryVectorIndexError("memory vector index is disabled")
        identity = self._require_identity("scrolling")
        self._ensure_collection()
        body: Dict[str, Any] = {
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
            "filter": {
                "must": [
                    {"key": "tenant_id", "match": {"value": identity.tenant_id}},
                    {"key": "owner_user_id", "match": {"value": identity.user_id}},
                ]
            },
        }
        if offset is not None:
            body["offset"] = offset
        try:
            response = self._request("POST", f"{self._collection_url()}/points/scroll", body)
        except httpx.HTTPError as exc:
            raise MemoryVectorIndexError(str(exc)) from exc
        result = response.get("result") or {}
        points = [
            {
                "point_id": item.get("id"),
                "payload": item.get("payload") or {},
            }
            for item in (result.get("points") or [])
        ]
        next_offset = result.get("next_page_offset")
        return points, None if next_offset is None else str(next_offset)

    def delete_point(self, point_id: str) -> None:
        """Delete one point by its id, inside the caller's tenant/user scope.

        Used only by reconciliation, which finds points by id rather than by
        memory: an orphaned or duplicated point may have no canonical memory
        left to name it.
        """
        if not self._enabled:
            raise MemoryVectorIndexError("memory vector index is disabled")
        self._require_identity("deletion")
        self._ensure_collection()
        try:
            self._request(
                "POST",
                f"{self._collection_url()}/points/delete?wait=true",
                {"points": [point_id]},
            )
        except httpx.HTTPError as exc:
            raise MemoryVectorIndexError(str(exc)) from exc

    def delete_memory(self, memory_id: str) -> None:
        """Delete one memory point inside the caller's tenant/user scope."""
        if not self._enabled:
            raise MemoryVectorIndexError("memory vector index is disabled")
        identity = self._require_identity("deletion")
        self._ensure_collection()
        try:
            self._request(
                "POST",
                f"{self._collection_url()}/points/delete?wait=true",
                {
                    "filter": {
                        "must": [
                            {"key": "memory_id", "match": {"value": memory_id}},
                            {"key": "tenant_id", "match": {"value": identity.tenant_id}},
                            {"key": "owner_user_id", "match": {"value": identity.user_id}},
                        ]
                    }
                },
            )
        except httpx.HTTPError as exc:
            raise MemoryVectorIndexError(str(exc)) from exc
