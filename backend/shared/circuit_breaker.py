"""Circuit Breaker pattern implementation for fault-tolerant inter-service communication.

Prevents cascading failures by failing fast when a downstream service is unhealthy.
States: CLOSED (normal) -> OPEN (fail-fast) -> HALF_OPEN (probing recovery).

Usage:
    cb = CircuitBreaker(name="embedding", failure_threshold=5, recovery_timeout=30.0)

    try:
        result = cb.call(lambda: service_client.request("embedding_requests", payload))
    except CircuitBreakerOpen:
        return {"error": "Service temporarily unavailable"}
"""
import time
import threading
import logging
from enum import Enum
from typing import Callable, TypeVar, Any, Dict, Optional

logger = logging.getLogger("circuit_breaker")

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when the circuit is open and calls are being rejected."""
    def __init__(self, name: str, remaining_seconds: float):
        self.name = name
        self.remaining_seconds = remaining_seconds
        super().__init__(
            f"Circuit breaker '{name}' is OPEN. "
            f"Retry in {remaining_seconds:.1f}s"
        )


class CircuitBreaker:
    """
    Thread-safe circuit breaker with three states.

    CLOSED  — normal operation; tracks consecutive failures.
    OPEN    — all calls rejected immediately (fail-fast 503).
    HALF_OPEN — allows a limited number of probe calls to test recovery.

    Config:
        failure_threshold: consecutive failures before opening (default 5)
        recovery_timeout:  seconds before transitioning OPEN -> HALF_OPEN (default 30)
        half_open_max_calls: probe calls allowed in HALF_OPEN (default 3)
        success_threshold: consecutive successes in HALF_OPEN to close (default 2)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

        # Metrics counters
        self._total_calls = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_rejected = 0

    @property
    def state(self) -> CircuitState:
        """Current circuit state (may transition OPEN -> HALF_OPEN on read)."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    @property
    def metrics(self) -> Dict[str, Any]:
        """Snapshot of circuit breaker metrics for monitoring."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "total_calls": self._total_calls,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "opened_at": self._opened_at,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
            }

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function through the circuit breaker.

        Args:
            func: The callable to execute (e.g., service_client.request)
            *args, **kwargs: Arguments passed to func

        Returns:
            The return value of func

        Raises:
            CircuitBreakerOpen: If the circuit is open
            Exception: Any exception raised by func (after recording as failure)
        """
        with self._lock:
            self._total_calls += 1
            self._check_state_transition()

            if self._state == CircuitState.OPEN:
                remaining = self.recovery_timeout - (time.monotonic() - self._opened_at)
                self._total_rejected += 1
                raise CircuitBreakerOpen(self.name, max(0.0, remaining))

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    self._total_rejected += 1
                    raise CircuitBreakerOpen(self.name, 0.0)
                self._half_open_calls += 1

        # Execute outside the lock to avoid holding it during I/O
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._total_successes += 1

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            else:
                # Reset failure count on success in CLOSED state
                self._failure_count = 0

    def _on_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in HALF_OPEN reopens immediately
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def _check_state_transition(self) -> None:
        """Check if OPEN -> HALF_OPEN transition is due (called under lock)."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state (called under lock)."""
        old_state = self._state
        self._state = new_state

        if new_state == CircuitState.OPEN:
            self._opened_at = time.monotonic()
            self._success_count = 0
            self._half_open_calls = 0
            logger.warning(
                f"Circuit '{self.name}': {old_state.value} -> OPEN "
                f"(failures={self._failure_count}/{self.failure_threshold})"
            )
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
            logger.info(
                f"Circuit '{self.name}': OPEN -> HALF_OPEN "
                f"(probing with max {self.half_open_max_calls} calls)"
            )
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            logger.info(f"Circuit '{self.name}': {old_state.value} -> CLOSED (recovered)")

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)


class CircuitBreakerRegistry:
    """
    Registry of named circuit breakers for centralized management.

    Usage:
        registry = CircuitBreakerRegistry()
        cb = registry.get_or_create("embedding", failure_threshold=5)
        all_metrics = registry.get_all_metrics()
    """

    def __init__(self) -> None:
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_or_create(self, name: str, **kwargs: Any) -> CircuitBreaker:
        """Get an existing circuit breaker or create a new one."""
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name=name, **kwargs)
            return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name, or None if not found."""
        with self._lock:
            return self._breakers.get(name)

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all registered circuit breakers."""
        with self._lock:
            return {name: cb.metrics for name, cb in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers to CLOSED state."""
        with self._lock:
            for cb in self._breakers.values():
                cb.reset()
