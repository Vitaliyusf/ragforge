"""Factory for creating model cache instances."""
from app.cache.interfaces import IModelCache
from app.cache.memory import MemoryModelCache
from app.core.config import Settings


class ModelCacheFactory:
    """Factory for creating IModelCache instances."""

    @staticmethod
    def create(config: Settings, implementation: str = "memory") -> IModelCache:
        if implementation == "memory":
            return MemoryModelCache(config)
        raise ValueError(f"Unknown cache implementation: {implementation}")
