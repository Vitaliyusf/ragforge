"""LangChain embedding model implementation."""
from typing import List, Optional

try:
    from langchain_huggingface import HuggingFaceEmbeddings
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False
    HuggingFaceEmbeddings = None

from app.embedding.interfaces import IEmbeddingModel


class LangChainEmbeddingModel(IEmbeddingModel):
    """LangChain HuggingFace embeddings model."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize LangChain embedding model.
        
        Args:
            model_name: Name of the model to load
        """
        self.model_name = model_name
        self._model: Optional[HuggingFaceEmbeddings] = None
        self._load_model()
    
    def _load_model(self) -> None:
        """Load the LangChain embedding model."""
        if not HAS_LANGCHAIN:
            raise ImportError("langchain-huggingface is not available")
        
        try:
            self._model = HuggingFaceEmbeddings(model_name=self.model_name)
        except Exception as e:
            raise RuntimeError(f"Failed to load LangChain embedding model: {e}")
    
    def encode(self, text: str) -> List[float]:
        """Encode text to embedding vector."""
        if not self.is_loaded():
            return []
        return self._model.embed_query(text)
    
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None
