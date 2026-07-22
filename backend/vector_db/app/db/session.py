"""Vector store factory — returns the configured IVectorStore backend."""
from app.core.config import settings
from app.db.interfaces import IVectorStore


def get_vector_store() -> IVectorStore:
    """Instantiate and return the configured vector store backend.

    Controlled by the ``VECTOR_STORE_TYPE`` environment variable
    (default: ``qdrant``).  Valid values: ``qdrant`` | ``chromadb`` | ``in_memory``.
    """
    store_type = settings.vector_store_type.lower()

    if store_type == "qdrant":
        from app.db.implementations.qdrant import QdrantVectorStore

        return QdrantVectorStore(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection_name=settings.qdrant_collection_name,
            vector_size=settings.qdrant_vector_size,
            api_key=settings.qdrant_api_key,
            https=settings.qdrant_https,
        )

    if store_type == "chromadb":
        from app.db.implementations.chromadb import ChromaDBVectorStore

        return ChromaDBVectorStore(
            collection_name=settings.qdrant_collection_name,
        )

    if store_type == "in_memory":
        from app.db.implementations.in_memory import InMemoryVectorStore

        return InMemoryVectorStore(
            collection_name=settings.qdrant_collection_name,
        )

    raise ValueError(
        f"Unknown vector_store_type '{store_type}'. "
        "Valid values: qdrant | chromadb | in_memory"
    )
