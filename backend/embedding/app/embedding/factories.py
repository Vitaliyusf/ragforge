"""Factory for creating embedding models."""
import logging
from typing import Optional

from app.embedding.interfaces import IEmbeddingModel
from app.embedding.implementations.sentence_transformers import SentenceTransformerModel
from app.embedding.implementations.langchain import LangChainEmbeddingModel
from app.config import EmbeddingConfig

logger = logging.getLogger(__name__)


class EmbeddingModelFactory:
    """Factory for creating embedding model instances."""
    
    @staticmethod
    def create(config: EmbeddingConfig) -> Optional[IEmbeddingModel]:
        """
        Create an embedding model instance.
        
        Args:
            config: Service configuration
            
        Returns:
            Embedding model instance or None if no model available
        """
        model_type = config.model_type.lower()
        model_name = config.model_name
        
        # Try sentence-transformers first if auto or explicitly requested
        if model_type in ("auto", "sentence_transformers"):
            try:
                return SentenceTransformerModel(model_name)
            except Exception as e:
                logger.warning("Failed to load sentence-transformers model: %s", e)
                if model_type == "sentence_transformers":
                    return None  # Explicitly requested, don't fallback
        
        # Fallback to LangChain if auto or explicitly requested
        if model_type in ("auto", "langchain"):
            try:
                return LangChainEmbeddingModel(model_name)
            except Exception as e:
                logger.warning("Failed to load LangChain model: %s", e)
                return None
        
        return None
