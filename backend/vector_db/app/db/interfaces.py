"""Vector store interfaces for chunk-native operations."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import numpy as np


class IVectorStore(ABC):
    """Interface for chunk storage and retrieval operations."""

    @abstractmethod
    def initialize_collection(self) -> str:
        """Ensure the backing collection and indexes exist."""
        raise NotImplementedError

    @property
    @abstractmethod
    def collection_name(self) -> str:
        """Return the active collection name."""
        raise NotImplementedError

    @abstractmethod
    def upsert_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Upsert chunk points into the backing store."""
        raise NotImplementedError

    @abstractmethod
    def search_chunks(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        include_payload: bool = True,
        include_vector: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks using the mandatory internal safety filter."""
        raise NotImplementedError

    @abstractmethod
    def delete_chunks(self, filters: Dict[str, Any]) -> int:
        """Hard delete chunks using a document/file filter."""
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        """Get the number of stored points."""
        raise NotImplementedError
