"""Document store session management."""
from app.db.interfaces import IDocumentStore
from app.db.implementations.in_memory import InMemoryDocumentStore
from app.core.config import RAGConfig


def get_document_store(config: RAGConfig) -> IDocumentStore:
    """
    Get or create a document store instance.
    
    Args:
        config: RAG configuration
        
    Returns:
        Document store instance
    """
    store_type = config.vector_store_type.lower()
    
    if store_type == "in_memory":
        return InMemoryDocumentStore()
    else:
        raise ValueError(f"Unknown document store type: {store_type}")
