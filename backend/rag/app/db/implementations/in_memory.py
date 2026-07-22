"""In-memory document store implementation."""
import numpy as np
from typing import List, Dict, Any

from app.db.interfaces import IDocumentStore


class InMemoryDocumentStore(IDocumentStore):
    """In-memory document store."""
    
    def __init__(self):
        """Initialize the document store."""
        self._documents: List[Dict[str, Any]] = []
    
    def add_document(self, text: str, embedding: np.ndarray) -> None:
        """Add a document with its embedding."""
        self._documents.append({
            "text": text,
            "embedding": embedding
        })
    
    def search(self, query_embedding: np.ndarray, top_k: int = 3) -> List[str]:
        """Search for similar documents using cosine similarity."""
        similarities = []
        
        for doc in self._documents:
            doc_embedding = doc["embedding"]
            similarity = self._cosine_similarity(query_embedding, doc_embedding)
            similarities.append((similarity, doc["text"]))
        
        # Sort by similarity descending and get top_k
        similarities.sort(reverse=True)
        return [text for _, text in similarities[:top_k]]
    
    def count(self) -> int:
        """Get the number of documents."""
        return len(self._documents)
    
    @staticmethod
    def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)
