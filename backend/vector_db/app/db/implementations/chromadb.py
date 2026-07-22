"""ChromaDB vector store implementation of IVectorStore."""
import logging
from typing import Any, Dict, List, Optional

import numpy as np

from app.core.constants import DEFAULT_COLLECTION_NAME
from app.db.interfaces import IVectorStore

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    _CHROMADB_AVAILABLE = True
except ImportError:
    _CHROMADB_AVAILABLE = False


class ChromaDBVectorStore(IVectorStore):
    """ChromaDB-backed implementation of IVectorStore.

    Uses cosine similarity and stores all required chunk payload fields
    as ChromaDB metadata (stringified where necessary).
    """

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        if not _CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb is not installed. Install it with: pip install chromadb"
            )

        import os

        os.makedirs(persist_directory, exist_ok=True)
        self._collection_name = collection_name
        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # IVectorStore interface
    # ------------------------------------------------------------------

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def initialize_collection(self) -> str:
        """ChromaDB creates the collection on construction; this is a no-op."""
        return self._collection_name

    def upsert_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Upsert chunks using chunk_id as the deterministic ChromaDB document ID."""
        if not chunks:
            return 0

        ids: List[str] = []
        embeddings: List[List[float]] = []
        metadatas: List[Dict[str, str]] = []
        documents: List[str] = []

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            if not chunk_id:
                raise ValueError("chunk_id is required")
            embedding = chunk.get("embedding")
            if embedding is None:
                raise ValueError("embedding is required")
            text = chunk.get("text", "")

            tenant_id = chunk.get("tenant_id")
            if not tenant_id or not chunk.get("owner_user_id") or not chunk.get("owner_admin_id"):
                raise ValueError("tenant and owner fields are required")
            ids.append(f"{tenant_id}:{chunk_id}")
            embeddings.append(np.asarray(embedding, dtype=np.float32).tolist())
            metadatas.append(self._build_metadata(chunk))
            documents.append(text)

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )
        return len(ids)

    def search_chunks(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        include_payload: bool = True,
        include_vector: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search using cosine similarity with an optional metadata filter."""
        query_list = np.asarray(query_vector, dtype=np.float32).tolist()
        where = self._build_where_clause(filters) if filters else None

        include_fields = ["metadatas", "distances"]
        if include_vector:
            include_fields.append("embeddings")

        results = self._collection.query(
            query_embeddings=[query_list],
            n_results=top_k,
            where=where,
            include=include_fields,
        )

        formatted: List[Dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas_list = results.get("metadatas", [[]])[0]
        embeddings_list = results.get("embeddings", [[]] if include_vector else None)
        if embeddings_list:
            embeddings_list = embeddings_list[0]

        for i, doc_id in enumerate(ids):
            distance = distances[i] if i < len(distances) else 0.0
            score = 1.0 - float(distance)  # cosine distance → similarity
            item: Dict[str, Any] = {"id": doc_id, "score": score}
            if include_payload and i < len(metadatas_list):
                item["payload"] = dict(metadatas_list[i])
            if include_vector and embeddings_list and i < len(embeddings_list):
                item["vector"] = embeddings_list[i]
            formatted.append(item)

        return formatted

    def delete_chunks(self, filters: Dict[str, Any]) -> int:
        """Hard delete chunks by file_id, document_id, or both."""
        file_id = filters.get("file_id")
        document_id = filters.get("document_id")

        if not file_id and not document_id:
            raise ValueError("delete_chunks requires file_id, document_id, or both")

        where = self._build_where_clause(filters)
        existing = self._collection.get(where=where, include=[])
        ids = existing.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        """Return the total number of stored chunks."""
        try:
            return self._collection.count()
        except Exception as exc:
            logger.error("ChromaDB count failed: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_metadata(chunk: Dict[str, Any]) -> Dict[str, str]:
        """Flatten chunk fields into a ChromaDB-compatible string metadata dict."""
        fields = (
            "tenant_id", "owner_user_id", "owner_admin_id",
            "file_id", "document_id", "chunk_id", "chunk_index", "chunk_version",
            "text_preview", "source_name", "page", "section",
            "retrieval_allowed", "review_status", "issue_flags", "created_at",
        )
        meta: Dict[str, str] = {}
        for key in fields:
            value = chunk.get(key)
            if value is None:
                meta[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                meta[key] = str(value)
            else:
                meta[key] = str(value)
        return meta

    @staticmethod
    def _build_where_clause(filters: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a filter dict to a ChromaDB $and where clause."""
        conditions = []
        for key, value in filters.items():
            if isinstance(value, list):
                conditions.append({key: {"$in": [str(v) for v in value]}})
            else:
                conditions.append({key: {"$eq": str(value)}})

        if not conditions:
            return {}
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}
