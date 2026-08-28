"""Factory for creating embedding models."""
import logging
import time
from typing import Callable, Optional

from app.embedding.interfaces import IEmbeddingModel
from app.embedding.implementations.sentence_transformers import SentenceTransformerModel
from app.config import EmbeddingConfig

logger = logging.getLogger(__name__)

# Loading normally reads the model baked into the image, but an EMBEDDING_MODEL
# override falls back to a huggingface fetch that can fail transiently. Retry a
# few times so one bad response does not leave the service permanently unable to
# embed, while staying bounded so startup cannot hang.
MODEL_LOAD_MAX_ATTEMPTS = 3
MODEL_LOAD_RETRY_DELAY_SECONDS = 2.0


def _load_with_retry(
    build: Callable[[], IEmbeddingModel], description: str
) -> Optional[IEmbeddingModel]:
    """Build a model, retrying transient load failures a bounded number of times."""
    for attempt in range(1, MODEL_LOAD_MAX_ATTEMPTS + 1):
        try:
            return build()
        except Exception as e:
            if attempt < MODEL_LOAD_MAX_ATTEMPTS:
                logger.warning(
                    "Failed to load %s model (attempt %d/%d), retrying: %s",
                    description, attempt, MODEL_LOAD_MAX_ATTEMPTS, e,
                )
                time.sleep(MODEL_LOAD_RETRY_DELAY_SECONDS * attempt)
                continue
            logger.error(
                "Failed to load %s model after %d attempts: %s",
                description, MODEL_LOAD_MAX_ATTEMPTS, e,
            )
    return None


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

        if model_type not in ("auto", "sentence_transformers"):
            logger.error("Unsupported embedding model type: %s", model_type)
            return None

        return _load_with_retry(
            lambda: SentenceTransformerModel(model_name), "sentence-transformers"
        )
