"""Qdrant vector store implementation for chunk-native operations."""
import uuid
from typing import Any, Dict, List, Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    PointStruct,
    VectorParams,
)

from app.core.constants import (
    ALLOWED_CALLER_FILTERS,
    ALLOWED_REVIEW_STATUSES,
    DEFAULT_COLLECTION_NAME,
    INDEXED_FIELDS,
    PAYLOAD_FIELDS,
    SAFE_REVIEW_STATUSES,
)
from app.db.interfaces import IVectorStore, verify_targets


class QdrantVectorStore(IVectorStore):
    """Qdrant-backed chunk store."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        vector_size: int = 384,
        api_key: Optional[str] = None,
        https: bool = False,
    ) -> None:
        self.client = QdrantClient(
            host=host,
            port=port,
            api_key=api_key or None,
            https=https,
        )
        self._collection_name = collection_name or DEFAULT_COLLECTION_NAME
        self._vector_size = vector_size
        self.initialize_collection()

    # ------------------------------------------------------------------
    # IVectorStore interface
    # ------------------------------------------------------------------

    @property
    def collection_name(self) -> str:
        """Return the active collection name."""
        return self._collection_name

    def initialize_collection(self) -> str:
        """Ensure the collection and payload indexes exist."""
        existing = {c.name for c in self.client.get_collections().collections}
        if self._collection_name not in existing:
            self.client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=self._vector_size,
                    distance=Distance.COSINE,
                ),
            )
        self._ensure_payload_indexes()
        return self._collection_name

    def upsert_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Upsert chunks as deterministic Qdrant points."""
        if not chunks:
            return 0

        points: List[PointStruct] = []
        for chunk in chunks:
            payload = self._build_payload(chunk)
            embedding = self._normalize_embedding(chunk.get("embedding", []))
            points.append(
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{payload['tenant_id']}:{payload['chunk_id']}")),
                    vector=embedding,
                    payload=payload,
                )
            )

        self.client.upsert(collection_name=self._collection_name, points=points)
        return len(points)

    def search_chunks(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        include_payload: bool = True,
        include_vector: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search for chunks while enforcing the internal retrieval safety filter."""
        query_list = np.asarray(query_vector, dtype=np.float32).tolist()
        if len(query_list) != self._vector_size:
            raise ValueError(
                f"Query vector size mismatch: expected {self._vector_size}, got {len(query_list)}"
            )

        # `client.search` was removed in qdrant-client 1.19; `query_points` is
        # the replacement and returns the hits under `.points`.
        search_results = self.client.query_points(
            collection_name=self._collection_name,
            query=query_list,
            limit=top_k,
            query_filter=self._build_search_filter(filters),
            with_payload=include_payload,
            with_vectors=include_vector,
        ).points

        formatted: List[Dict[str, Any]] = []
        for result in search_results:
            item: Dict[str, Any] = {"id": str(result.id), "score": float(result.score)}
            if include_payload:
                item["payload"] = result.payload or {}
            if include_vector:
                vector = result.vector
                if hasattr(vector, "tolist"):
                    vector = vector.tolist()
                item["vector"] = vector
            formatted.append(item)

        return formatted

    def delete_chunks(self, filters: Dict[str, Any]) -> int:
        """Hard delete chunks by file/document filter."""
        delete_filter = self._build_delete_filter(filters)
        ids = self._scroll_ids(delete_filter)
        if not ids:
            return 0
        self.client.delete(collection_name=self._collection_name, points_selector=ids)
        return len(ids)

    def lookup_ids(
        self,
        field: str,
        values: List[str],
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[str]]:
        """Report which of ``values`` exist in the caller's scope.

        The scroll filter is built from the scope conditions **and** a
        ``match: any`` over the supplied ids, so Qdrant never returns a point
        the caller did not name. Only the matched field and the two safety
        flags are read back — no chunk text, no ownership, nothing the caller
        could not already see through search.
        """
        wanted = verify_targets(field, values)
        if not wanted:
            return {"present": [], "retrievable": []}

        must: List[FieldCondition] = [
            FieldCondition(key=field, match={"any": sorted(wanted)}),
        ]
        for key, value in (filters or {}).items():
            if key in ALLOWED_CALLER_FILTERS and value is not None:
                must.append(FieldCondition(key=key, match={"value": value}))

        present: set = set()
        retrievable: set = set()
        offset = None
        while True:
            records, next_offset = self.client.scroll(
                collection_name=self._collection_name,
                scroll_filter=Filter(must=must),
                offset=offset,
                limit=256,
                with_payload=[field, "retrieval_allowed", "review_status"],
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                value = payload.get(field)
                if value is None or str(value) not in wanted:
                    continue
                present.add(str(value))
                if payload.get("retrieval_allowed") and payload.get(
                    "review_status"
                ) != "removed":
                    retrievable.add(str(value))
            if next_offset is None:
                break
            offset = next_offset

        return {"present": sorted(present), "retrievable": sorted(retrievable)}

    def count(self) -> int:
        """Return the number of points in the active collection."""
        count_error: Optional[Exception] = None
        try:
            result = self.client.count(collection_name=self._collection_name, exact=True)
            return int(getattr(result, "count", 0) or 0)
        except Exception as exc:
            count_error = exc

        try:
            info = self.client.get_collection(self._collection_name)
            return int(getattr(info, "points_count", 0) or 0)
        except Exception:
            if count_error is not None:
                raise count_error
            raise

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_payload_indexes(self) -> None:
        for field_name, schema in INDEXED_FIELDS.items():
            self.client.create_payload_index(
                collection_name=self._collection_name,
                field_name=field_name,
                field_schema=schema,
            )

    def _require_string(self, chunk: Dict[str, Any], key: str) -> str:
        value = chunk.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{key} is required")
        return value

    def _normalize_embedding(self, embedding: Any) -> List[float]:
        vector = np.asarray(embedding, dtype=np.float32).tolist()
        if len(vector) != self._vector_size:
            raise ValueError(
                f"Vector size mismatch: expected {self._vector_size}, got {len(vector)}"
            )
        return vector

    def _build_payload(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        file_id = self._require_string(chunk, "file_id")
        tenant_id = self._require_string(chunk, "tenant_id")
        owner_user_id = self._require_string(chunk, "owner_user_id")
        owner_admin_id = self._require_string(chunk, "owner_admin_id")
        document_id = self._require_string(chunk, "document_id")
        chunk_id = self._require_string(chunk, "chunk_id")
        source_name = self._require_string(chunk, "source_name")

        text = chunk.get("text")
        if not isinstance(text, str):
            raise ValueError("text is required")

        text_preview = chunk.get("text_preview")
        if not isinstance(text_preview, str) or not text_preview:
            text_preview = text[:250]

        retrieval_allowed = chunk.get("retrieval_allowed")
        if not isinstance(retrieval_allowed, bool):
            raise ValueError("retrieval_allowed must be a boolean")

        review_status = chunk.get("review_status")
        if review_status not in ALLOWED_REVIEW_STATUSES:
            raise ValueError("review_status is invalid")

        issue_flags = chunk.get("issue_flags", []) or []
        if not isinstance(issue_flags, list) or any(
            not isinstance(f, str) for f in issue_flags
        ):
            raise ValueError("issue_flags must be a list of strings")

        created_at = chunk.get("created_at")
        if not isinstance(created_at, str) or not created_at:
            raise ValueError("created_at is required")

        payload = {
            "tenant_id": tenant_id,
            "owner_user_id": owner_user_id,
            "owner_admin_id": owner_admin_id,
            "file_id": file_id,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "chunk_index": int(chunk.get("chunk_index", 0)),
            "chunk_version": int(chunk.get("chunk_version")),
            "text": text,
            "text_preview": text_preview,
            "source_name": source_name,
            "page": chunk.get("page"),
            "section": chunk.get("section"),
            "retrieval_allowed": retrieval_allowed,
            "review_status": review_status,
            "issue_flags": issue_flags,
            "created_at": created_at,
        }
        return {field: payload[field] for field in PAYLOAD_FIELDS}

    def _normalize_match_value(self, key: str, value: Any) -> Optional[Any]:
        if value is None:
            return None

        if key == "review_status":
            if isinstance(value, list):
                safe = [v for v in value if v in SAFE_REVIEW_STATUSES]
                return {"any": safe} if safe else None
            return {"value": value} if value in SAFE_REVIEW_STATUSES else None

        if isinstance(value, list):
            filtered = [v for v in value if v is not None]
            return {"any": filtered} if filtered else None

        return {"value": value}

    def _build_search_filter(self, filters: Optional[Dict[str, Any]]) -> Filter:
        must: List[FieldCondition] = [
            FieldCondition(key="retrieval_allowed", match={"value": True}),
        ]
        must_not: List[FieldCondition] = [
            FieldCondition(key="review_status", match={"value": "removed"}),
        ]

        for key, value in (filters or {}).items():
            if key not in ALLOWED_CALLER_FILTERS:
                continue
            match = self._normalize_match_value(key, value)
            if match is None:
                continue
            must.append(FieldCondition(key=key, match=match))

        return Filter(must=must, must_not=must_not)

    def _build_delete_filter(self, filters: Dict[str, Any]) -> Filter:
        file_id = filters.get("file_id")
        document_id = filters.get("document_id")

        must: List[FieldCondition] = []
        if file_id:
            must.append(FieldCondition(key="file_id", match={"value": file_id}))
        if document_id:
            must.append(FieldCondition(key="document_id", match={"value": document_id}))

        for field in ("tenant_id", "owner_user_id", "owner_admin_id"):
            if filters.get(field):
                must.append(FieldCondition(key=field, match={"value": filters[field]}))

        if not file_id and not document_id:
            raise ValueError("delete_chunks requires file_id, document_id, or both")

        return Filter(must=must)

    def _scroll_ids(self, scroll_filter: Filter) -> List[Any]:
        ids: List[Any] = []
        offset = None

        while True:
            records, next_offset = self.client.scroll(
                collection_name=self._collection_name,
                scroll_filter=scroll_filter,
                offset=offset,
                limit=256,
                with_payload=False,
                with_vectors=False,
            )
            ids.extend(record.id for record in records)
            if next_offset is None:
                break
            offset = next_offset

        return ids

