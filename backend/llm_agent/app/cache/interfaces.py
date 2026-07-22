"""Abstract interface for model cache."""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional


class IModelCache(ABC):
    """Interface for caching available model lists."""

    @abstractmethod
    def is_valid(self) -> bool:
        """Return True if the cache holds fresh data (not expired)."""

    @abstractmethod
    def set_models(self, models: List) -> None:
        """Store a list of models and record the current timestamp."""

    @abstractmethod
    def get_models(self) -> List:
        """Return the cached model list (may be empty if never populated)."""

    @abstractmethod
    def get_last_updated(self) -> Optional[datetime]:
        """Return the datetime when the cache was last populated, or None."""
