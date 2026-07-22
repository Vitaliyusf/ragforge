"""TTL-based idempotency cache for Kafka message deduplication.

Prevents duplicate processing when Kafka redelivers messages (at-least-once semantics).
Uses an in-memory dict with TTL expiry — no external dependencies required.

Usage:
    cache = IdempotencyCache(ttl_seconds=300)  # 5-minute dedup window

    if cache.is_duplicate(correlation_id):
        logger.info(f"Duplicate message {correlation_id}, skipping")
        return
    cache.mark_processed(correlation_id)
    # ... process message ...
"""
import time
import threading
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger("deduplication")


class IdempotencyCache:
    """
    Thread-safe TTL-based cache for tracking processed message IDs.

    Automatically evicts expired entries on access to prevent memory leaks.
    For high-throughput scenarios, also runs periodic cleanup.

    Args:
        ttl_seconds: Time-to-live for cache entries (default 300s = 5 min)
        max_size: Maximum entries before forced eviction (default 10000)
        cleanup_interval: Seconds between automatic cleanups (default 60s)
    """

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        max_size: int = 10000,
        cleanup_interval: float = 60.0,
    ):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.cleanup_interval = cleanup_interval

        self._cache: Dict[str, float] = {}  # key -> expiry timestamp
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

        # Metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def is_duplicate(self, key: str) -> bool:
        """
        Check if a message ID has already been processed.

        Args:
            key: The correlation_id or message ID to check

        Returns:
            True if the key was recently processed (duplicate), False otherwise
        """
        self._maybe_cleanup()

        with self._lock:
            if key in self._cache:
                expiry = self._cache[key]
                if time.monotonic() < expiry:
                    self._hits += 1
                    return True
                else:
                    # Expired entry — remove it
                    del self._cache[key]

            self._misses += 1
            return False

    def mark_processed(self, key: str, ttl_override: Optional[float] = None) -> None:
        """
        Mark a message ID as processed.

        Args:
            key: The correlation_id or message ID
            ttl_override: Optional custom TTL for this specific entry
        """
        ttl = ttl_override if ttl_override is not None else self.ttl_seconds

        with self._lock:
            self._cache[key] = time.monotonic() + ttl

            # Forced eviction if cache is too large
            if len(self._cache) > self.max_size:
                self._evict_oldest()

    def _maybe_cleanup(self) -> None:
        """Run periodic cleanup of expired entries."""
        now = time.monotonic()
        if now - self._last_cleanup < self.cleanup_interval:
            return

        with self._lock:
            self._last_cleanup = now
            expired_keys = [
                key for key, expiry in self._cache.items()
                if now >= expiry
            ]
            for key in expired_keys:
                del self._cache[key]
                self._evictions += 1

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired dedup entries")

    def _evict_oldest(self) -> None:
        """Evict the oldest 20% of entries when max_size is exceeded (called under lock)."""
        evict_count = max(1, len(self._cache) // 5)
        sorted_entries = sorted(self._cache.items(), key=lambda x: x[1])

        for key, _ in sorted_entries[:evict_count]:
            del self._cache[key]
            self._evictions += 1

        logger.warning(
            f"Dedup cache size exceeded {self.max_size}, evicted {evict_count} entries"
        )

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        return len(self._cache)

    @property
    def metrics(self) -> Dict[str, Any]:
        """Cache metrics for monitoring."""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate": self._hits / max(1, self._hits + self._misses),
            }

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()
