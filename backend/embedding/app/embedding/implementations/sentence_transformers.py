"""Sentence transformers embedding model implementation."""
from typing import List, Optional

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    SentenceTransformer = None

from app.embedding.interfaces import IEmbeddingModel


class SentenceTransformerModel(IEmbeddingModel):
    """Sentence transformers embedding model."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize sentence transformers model.
        
        Args:
            model_name: Name of the model to load
        """
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._load_model()
    
    def _load_model(self) -> None:
        """Load the sentence transformers model."""
        if not HAS_SENTENCE_TRANSFORMERS:
            raise ImportError("sentence-transformers is not available")
        
        try:
            self._model = SentenceTransformer(self.model_name)
        except Exception as e:
            raise RuntimeError(f"Failed to load sentence transformers model: {e}")
    
    def encode(self, text: str) -> List[float]:
        """Encode text to embedding vector."""
        if not self.is_loaded():
            return []
        return self._model.encode(text, normalize_embeddings=True).tolist()
    
    def encode_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Encode multiple texts in batch for better performance."""
        if not self.is_loaded() or not texts:
            return []
        import numpy as np
        embeddings = self._model.encode(texts, batch_size=batch_size, normalize_embeddings=True)
        if isinstance(embeddings, np.ndarray) and embeddings.ndim == 1:
            return [embeddings.tolist()]
        return [emb.tolist() for emb in embeddings]
    
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None
