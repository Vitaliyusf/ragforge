"""In-memory model cache implementation."""
import time
from datetime import datetime
from typing import List, Optional

from app.cache.interfaces import IModelCache
from app.core.config import Settings


class MemoryModelCache(IModelCache):
    """Simple TTL-based in-memory cache for model lists."""

    def __init__(self, config: Settings) -> None:
        self._models: List = []
        self._last_updated: Optional[datetime] = None
        self._last_updated_ts: Optional[float] = None
        self._ttl: int = config.models_cache_ttl

    def is_valid(self) -> bool:
        if self._last_updated_ts is None:
            return False
        return (time.monotonic() - self._last_updated_ts) < self._ttl

    def set_models(self, models: List) -> None:
        self._models = list(models)
        self._last_updated = datetime.utcnow()
        self._last_updated_ts = time.monotonic()

    def get_models(self) -> List:
        return list(self._models)

    def get_last_updated(self) -> Optional[datetime]:
        return self._last_updated
