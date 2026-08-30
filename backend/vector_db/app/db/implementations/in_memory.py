"""In-memory vector store implementation of IVectorStore.

Intended for development and unit testing only — O(n) linear scan,
not suitable for more than ~1 000 vectors.
"""
from typing import Any, Dict, List, Optional

import numpy as np

from app.core.constants import DEFAULT_COLLECTION_NAME
from app.db.interfaces import IVectorStore, verify_targets
from shared.sparse_retrieval import sparse_lexical_vector


class InMemoryVectorStore(IVectorStore):
    """Pure-Python in-memory store backed by a dict.

    All four IVectorStore operations are implemented so this class can
    be used as a drop-in substitute for Qdrant/ChromaDB in tests.
    """

    def __init__(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> None:
        self._collection_name = collection_name
        # { chunk_id: {"embedding": np.ndarray, "payload": dict} }
        self._store: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # IVectorStore interface
    # ------------------------------------------------------------------

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def initialize_collection(self) -> str:
        """No-op — the in-memory store is always ready."""
        return self._collection_name

    def upsert_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Upsert chunks keyed by chunk_id."""
        if not chunks:
            return 0

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            if not chunk_id:
                raise ValueError("chunk_id is required")
            embedding = chunk.get("embedding")
            if embedding is None:
                raise ValueError("embedding is required")

            tenant_id = chunk.get("tenant_id")
            if not tenant_id or not chunk.get("owner_user_id") or not chunk.get("owner_admin_id"):
                raise ValueError("tenant and owner fields are required")
            self._store[f"{tenant_id}:{chunk_id}"] = {
                "embedding": np.asarray(embedding, dtype=np.float32),
                "sparse": sparse_lexical_vector(str(chunk.get("text", ""))),
                "payload": {k: v for k, v in chunk.items() if k != "embedding"},
            }

        return len(chunks)

    def search_chunks(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        include_payload: bool = True,
        include_vector: bool = False,
    ) -> List[Dict[str, Any]]:
        """Linear cosine-similarity scan with optional payload filtering.

        The mandatory safety filter (retrieval_allowed=True, review_status!='removed')
        mirrors the Qdrant implementation so behaviour is consistent across backends.
        """
        query = np.asarray(query_vector, dtype=np.float32)
        results: List[Dict[str, Any]] = []

        for chunk_id, entry in self._store.items():
            payload = entry["payload"]

            # Mandatory safety filter
            if not payload.get("retrieval_allowed", False):
                continue
            if payload.get("review_status") == "removed":
                continue

            # Caller-supplied filters
            if filters and not self._matches_filters(payload, filters):
                continue

            score = float(self._cosine_similarity(query, entry["embedding"]))
            item: Dict[str, Any] = {"id": chunk_id, "score": score}
            if include_payload:
                item["payload"] = dict(payload)
            if include_vector:
                item["vector"] = entry["embedding"].tolist()
            results.append(item)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def search_sparse(
        self,
        query_sparse: Dict[str, List[Any]],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        include_payload: bool = True,
    ) -> List[Dict[str, Any]]:
        """Linear sparse dot-product search used by tests and local runs."""
        query = dict(zip(query_sparse.get("indices", []), query_sparse.get("values", [])))
        if not query:
            return []
        results: List[Dict[str, Any]] = []
        for point_id, entry in self._store.items():
            payload = entry["payload"]
            if not payload.get("retrieval_allowed", False) or payload.get("review_status") == "removed":
                continue
            if filters and not self._matches_filters(payload, filters):
                continue
            document = dict(zip(entry["sparse"]["indices"], entry["sparse"]["values"]))
            score = float(sum(value * document.get(index, 0.0) for index, value in query.items()))
            if score <= 0.0:
                continue
            item: Dict[str, Any] = {"id": point_id, "score": score}
            if include_payload:
                item["payload"] = dict(payload)
            results.append(item)
        results.sort(key=lambda item: (-item["score"], str(item["id"])))
        return results[:top_k]

    def delete_chunks(self, filters: Dict[str, Any]) -> int:
        """Hard delete chunks matching file_id, document_id, or both."""
        file_id = filters.get("file_id")
        document_id = filters.get("document_id")

        if not file_id and not document_id:
            raise ValueError("delete_chunks requires file_id, document_id, or both")

        to_delete = [
            cid
            for cid, entry in self._store.items()
            if self._matches_delete_filters(entry["payload"], file_id, document_id)
            and self._matches_filters(
                entry["payload"],
                {key: value for key, value in filters.items() if key not in {"file_id", "document_id"}},
            )
        ]
        for cid in to_delete:
            del self._store[cid]
        return len(to_delete)

    def lookup_ids(
        self,
        field: str,
        values: List[str],
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[str]]:
        """Report which of ``values`` exist under ``filters``.

        Mirrors the Qdrant implementation, including its safety split: the
        scope filters are applied before an id is reported present, so an id
        belonging to another tenant reads exactly like an id that was
        deleted — which is the point.
        """
        wanted = verify_targets(field, values)
        if not wanted:
            return {"present": [], "retrievable": []}

        scope = {
            key: value
            for key, value in (filters or {}).items()
            if value is not None
        }
        present: set = set()
        retrievable: set = set()
        for entry in self._store.values():
            payload = entry["payload"]
            value = payload.get(field)
            if value is None or str(value) not in wanted:
                continue
            if scope and not self._matches_filters(payload, scope):
                continue
            present.add(str(value))
            if payload.get("retrieval_allowed") and payload.get("review_status") != "removed":
                retrievable.add(str(value))

        return {"present": sorted(present), "retrievable": sorted(retrievable)}

    def count(self) -> int:
        return len(self._store)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_filters(payload: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for key, value in filters.items():
            if key not in payload:
                return False
            if isinstance(value, list):
                if payload[key] not in value:
                    return False
            elif payload[key] != value:
                return False
        return True

    @staticmethod
    def _matches_delete_filters(
        payload: Dict[str, Any],
        file_id: Optional[str],
        document_id: Optional[str],
    ) -> bool:
        if file_id and payload.get("file_id") != file_id:
            return False
        if document_id and payload.get("document_id") != document_id:
            return False
        return True

    @staticmethod
    def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))
