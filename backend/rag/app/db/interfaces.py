"""Document vector store interfaces."""
from abc import ABC, abstractmethod
from typing import List
import numpy as np


class IDocumentStore(ABC):
    """Interface for document storage with embeddings."""
    
    @abstractmethod
    def add_document(self, text: str, embedding: np.ndarray) -> None:
        """Add a document with its embedding."""
        pass
    
    @abstractmethod
    def search(self, query_embedding: np.ndarray, top_k: int = 3) -> List[str]:
        """
        Search for similar documents.
        
        Returns:
            List of document texts sorted by similarity
        """
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Get the number of documents."""
        pass
