"""Token-bucket rate limiter with FastAPI middleware.

Implements per-IP and global rate limiting to prevent abuse and protect
downstream services from overload.

Usage:
    from shared.rate_limiter import RateLimiterMiddleware

    app.add_middleware(
        RateLimiterMiddleware,
        global_rate=100.0,    # 100 req/s globally
        per_ip_rate=20.0,     # 20 req/s per IP
        burst_multiplier=2.0, # Allow 2x burst
    )
"""
import time
import threading
import logging
import ipaddress
import os
from typing import Any, Dict, Optional
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from shared.metrics import METRICS

logger = logging.getLogger("rate_limiter")

_SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown")


class TokenBucket:
    """
    Thread-safe token bucket algorithm.

    Tokens are added at a fixed rate. Each request consumes one token.
    When the bucket is empty, requests are rejected.

    Args:
        rate: tokens per second (refill rate)
        capacity: maximum tokens (burst capacity)
    """

    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> bool:
        """
        Try to consume tokens from the bucket.

        Returns:
            True if tokens were consumed, False if rate limited.
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._last_refill = now

            # Refill tokens based on elapsed time
            self._tokens = min(
                self.capacity,
                self._tokens + elapsed * self.rate
            )

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            return min(
                self.capacity,
                self._tokens + elapsed * self.rate
            )

    def time_until_available(self) -> float:
        """Seconds until at least 1 token is available."""
        with self._lock:
            if self._tokens >= 1.0:
                return 0.0
            deficit = 1.0 - self._tokens
            return deficit / self.rate if self.rate > 0 else float("inf")


class RateLimiter:
    """
    Rate limiter with global and per-IP buckets.

    Automatically cleans up stale per-IP buckets to prevent memory leaks.
    """

    def __init__(
        self,
        global_rate: float = 100.0,
        per_ip_rate: float = 20.0,
        burst_multiplier: float = 2.0,
        cleanup_interval: float = 300.0,
    ):
        self.global_rate = global_rate
        self.per_ip_rate = per_ip_rate
        self.burst_multiplier = burst_multiplier
        self.cleanup_interval = cleanup_interval

        # Global bucket
        self._global_bucket = TokenBucket(
            rate=global_rate,
            capacity=global_rate * burst_multiplier,
        )

        # Per-IP buckets
        self._ip_buckets: Dict[str, TokenBucket] = {}
        self._ip_last_seen: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

        # Metrics
        self._total_allowed = 0
        self._total_rejected = 0
        self._rejected_by_ip: Dict[str, int] = {}

    def check(self, client_ip: str) -> tuple[bool, Optional[float]]:
        """
        Check if a request from client_ip should be allowed.

        Returns:
            (allowed, retry_after)
            - allowed: True if request is permitted
            - retry_after: seconds until retry (only set when rejected)
        """
        self._maybe_cleanup()

        # Check global limit first
        if not self._global_bucket.consume():
            retry_after = self._global_bucket.time_until_available()
            self._total_rejected += 1
            METRICS.rate_limiter_rejected.labels(service=_SERVICE_NAME).inc()
            logger.warning(f"Global rate limit hit (retry_after={retry_after:.1f}s)")
            return False, retry_after

        # Check per-IP limit
        bucket = self._get_ip_bucket(client_ip)
        if not bucket.consume():
            retry_after = bucket.time_until_available()
            self._total_rejected += 1
            METRICS.rate_limiter_rejected.labels(service=_SERVICE_NAME).inc()
            with self._lock:
                self._rejected_by_ip[client_ip] = self._rejected_by_ip.get(client_ip, 0) + 1
            logger.warning(f"Per-IP rate limit hit for {client_ip} (retry_after={retry_after:.1f}s)")
            return False, retry_after

        self._total_allowed += 1
        METRICS.rate_limiter_allowed.labels(service=_SERVICE_NAME).inc()
        return True, None

    def _get_ip_bucket(self, client_ip: str) -> TokenBucket:
        """Get or create a token bucket for the given IP."""
        with self._lock:
            self._ip_last_seen[client_ip] = time.monotonic()
            if client_ip not in self._ip_buckets:
                self._ip_buckets[client_ip] = TokenBucket(
                    rate=self.per_ip_rate,
                    capacity=self.per_ip_rate * self.burst_multiplier,
                )
            return self._ip_buckets[client_ip]

    def _maybe_cleanup(self) -> None:
        """Remove stale IP buckets to prevent memory leaks."""
        now = time.monotonic()
        if now - self._last_cleanup < self.cleanup_interval:
            return

        with self._lock:
            self._last_cleanup = now
            stale_ips = [
                ip for ip, last_seen in self._ip_last_seen.items()
                if now - last_seen > self.cleanup_interval
            ]
            for ip in stale_ips:
                del self._ip_buckets[ip]
                del self._ip_last_seen[ip]
                self._rejected_by_ip.pop(ip, None)

            if stale_ips:
                logger.info(f"Cleaned up {len(stale_ips)} stale IP buckets")

    @property
    def metrics(self) -> Dict:
        """Rate limiter metrics for monitoring."""
        return {
            "total_allowed": self._total_allowed,
            "total_rejected": self._total_rejected,
            "active_ip_buckets": len(self._ip_buckets),
            "global_tokens_available": self._global_bucket.available_tokens,
            "top_rejected_ips": dict(
                sorted(self._rejected_by_ip.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
        }

    # Whitelist management
    _whitelist: set = set()

    def add_to_whitelist(self, ip: str) -> None:
        """Add an IP to the whitelist (bypass rate limiting)."""
        self._whitelist.add(ip)

    def is_whitelisted(self, ip: str) -> bool:
        """Check if an IP is whitelisted."""
        return ip in self._whitelist


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware for rate limiting.

    Adds Retry-After header and returns 429 when rate limited.
    Whitelists /health and /docs endpoints.
    """

    EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    def __init__(
        self,
        app: Any,
        global_rate: float = 100.0,
        per_ip_rate: float = 20.0,
        burst_multiplier: float = 2.0,
    ):
        super().__init__(app)
        self.limiter = RateLimiter(
            global_rate=global_rate,
            per_ip_rate=per_ip_rate,
            burst_multiplier=burst_multiplier,
        )
        self._trusted_proxies = []
        for raw_value in os.getenv("TRUSTED_PROXY_CIDRS", "127.0.0.1/32,::1/128").split(","):
            value = raw_value.strip()
            if not value:
                continue
            try:
                self._trusted_proxies.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                logger.error("Ignoring invalid trusted proxy CIDR")

    def _client_ip(self, request: Request) -> str:
        peer = request.client.host if request.client else "unknown"
        try:
            peer_address = ipaddress.ip_address(peer)
        except ValueError:
            return peer
        if not any(peer_address in network for network in self._trusted_proxies):
            return peer
        forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        try:
            return str(ipaddress.ip_address(forwarded)) if forwarded else peer
        except ValueError:
            return peer

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        client_ip = self._client_ip(request)

        # Check whitelist
        if self.limiter.is_whitelisted(client_ip):
            return await call_next(request)

        allowed, retry_after = self.limiter.check(client_ip)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "detail": "Rate limit exceeded. Please retry after the indicated time.",
                    "retry_after": round(retry_after, 1) if retry_after else 1.0,
                },
                headers={
                    "Retry-After": str(int(retry_after) + 1) if retry_after else "1",
                    "X-RateLimit-Limit": str(int(self.limiter.per_ip_rate)),
                },
            )

        response = await call_next(request)

        # Add rate limit headers to successful responses
        response.headers["X-RateLimit-Limit"] = str(int(self.limiter.per_ip_rate))
        response.headers["X-RateLimit-Remaining"] = str(
            int(self.limiter._get_ip_bucket(client_ip).available_tokens)
        )

        return response
