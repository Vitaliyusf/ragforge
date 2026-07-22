"""Embedding model interfaces."""
from abc import ABC, abstractmethod
from typing import List


class IEmbeddingModel(ABC):
    """Interface for embedding models."""
    
    @abstractmethod
    def encode(self, text: str) -> List[float]:
        """
        Encode text to embedding vector.
        
        Args:
            text: Text to encode
            
        Returns:
            Embedding vector as list of floats
        """
        pass
    
    def encode_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Encode multiple texts to embedding vectors. Default implementation
        falls back to encode() per text. Override for batch-optimized models.
        
        Args:
            texts: List of texts to encode
            batch_size: Batch size for encoding (used by implementations that support it)
            
        Returns:
            List of embedding vectors
        """
        return [self.encode(t) for t in texts]
    
    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        pass
