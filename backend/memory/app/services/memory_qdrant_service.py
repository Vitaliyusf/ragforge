"""Optional Qdrant integration for semantic memory retrieval."""
from __future__ import annotations

import hashlib
import math
import uuid
from typing import Any, Dict, List

import httpx

from app.core.config import settings
from shared.logging import ServiceLogger
from app.services.tenant_scope import current_identity


class MemoryQdrantIndex:
    """Small Qdrant client wrapper using the HTTP API."""

    def __init__(self, logger: ServiceLogger):
        self.logger = logger
        self._enabled = bool(settings.qdrant_enabled and settings.qdrant_url)
        self._collection_ready = False

    def is_enabled(self) -> bool:
        """Return whether Qdrant integration is enabled."""
        return self._enabled

    def _collection_url(self) -> str:
        return f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection_name}"

    def _request(self, method: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if settings.qdrant_api_key:
            headers["api-key"] = settings.qdrant_api_key

        with httpx.Client(timeout=settings.qdrant_timeout_seconds) as client:
            response = client.request(method, path, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    def _ensure_collection(self) -> None:
        if self._collection_ready or not self._enabled:
            return
        try:
            self._request(
                "PUT",
                self._collection_url(),
                {
                    "vectors": {
                        "size": settings.qdrant_vector_size,
                        "distance": "Cosine",
                    }
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 409:
                self.logger.log(
                    "memory_qdrant_service:_ensure_collection",
                    "Failed to ensure Qdrant collection",
                    {"error": str(exc), "collection": settings.qdrant_collection_name},
                    "W",
                )
                raise
        self._collection_ready = True

    def _tokenize(self, text: str) -> List[str]:
        return [token for token in text.lower().split() if token]

    def _embed_text(self, text: str) -> List[float]:
        vector = [0.0] * settings.qdrant_vector_size
        for token in self._tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % settings.qdrant_vector_size
            sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
            vector[index] += sign

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return vector
        return [value / magnitude for value in vector]

    def index_memory(self, memory_doc: Dict[str, Any]) -> bool:
        """Upsert a memory point into Qdrant."""
        if not self._enabled:
            return False
        try:
            self._ensure_collection()
            identity = current_identity()
            if identity is None:
                raise ValueError("Authenticated identity is required for memory indexing")
            payload = {
                "owner_id": memory_doc["owner_id"],
                "owner_type": memory_doc["owner_type"],
                "memory_id": memory_doc["id"],
                "memory_class": memory_doc["memory_class"],
                "text": memory_doc.get("content", {}).get("text", ""),
                "tags": memory_doc.get("tags", []),
                "importance": memory_doc.get("importance", 0.0),
                "updated_at": memory_doc.get("updated_at"),
                "archived": bool(memory_doc.get("archived_at")),
                "tenant_id": identity.tenant_id,
                "owner_user_id": identity.user_id,
                "owner_admin_id": identity.admin_id or identity.user_id,
            }
            point_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"memory:{identity.tenant_id}:{identity.user_id}:{memory_doc['id']}",
            ))
            self._request(
                "PUT",
                f"{self._collection_url()}/points?wait=true",
                {
                    "points": [
                        {
                            "id": point_id,
                            "vector": self._embed_text(payload["text"]),
                            "payload": payload,
                        }
                    ]
                },
            )
            return True
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.log(
                "memory_qdrant_service:index_memory",
                "Skipping Qdrant index update after request failure",
                {"memory_id": memory_doc.get("id"), "error": str(exc)},
                "W",
            )
            return False

    def search(self, query_text: str, owner_id: str, owner_type: str, limit: int) -> List[Dict[str, Any]]:
        """Search Qdrant for semantically similar memories."""
        if not self._enabled:
            return []
        try:
            self._ensure_collection()
            identity = current_identity()
            must = [
                {"key": "owner_id", "match": {"value": owner_id}},
                {"key": "owner_type", "match": {"value": owner_type}},
                {"key": "archived", "match": {"value": False}},
            ]
            if identity is not None:
                must.extend([
                    {"key": "tenant_id", "match": {"value": identity.tenant_id}},
                    {"key": "owner_user_id", "match": {"value": identity.user_id}},
                ])
            response = self._request(
                "POST",
                f"{self._collection_url()}/points/search",
                {
                    "vector": self._embed_text(query_text),
                    "limit": limit,
                    "with_payload": True,
                    "filter": {
                        "must": must
                    },
                },
            )
            results = response.get("result") or []
            return [
                {
                    "memory_id": (item.get("payload") or {}).get("memory_id") or item.get("id"),
                    "score": item.get("score", 0.0),
                    "payload": item.get("payload") or {},
                }
                for item in results
            ]
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.log(
                "memory_qdrant_service:search",
                "Returning no semantic memories after Qdrant search failure",
                {"owner_id": owner_id, "owner_type": owner_type, "error": str(exc)},
                "W",
            )
            return []

    def delete_memory(self, memory_id: str) -> None:
        """Delete a Qdrant point by memory id."""
        if not self._enabled:
            return
        try:
            self._ensure_collection()
            identity = current_identity()
            if identity is None:
                raise ValueError("Authenticated identity is required for memory deletion")
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
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.log(
                "memory_qdrant_service:delete_memory",
                "Skipping Qdrant delete after request failure",
                {"memory_id": memory_id, "error": str(exc)},
                "W",
            )
