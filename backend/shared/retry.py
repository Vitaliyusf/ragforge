"""Retry policy with exponential backoff and jitter.

Replaces fixed `time.sleep(2)` in consumer threads with configurable,
production-grade retry behavior.

Usage:
    policy = RetryPolicy(max_retries=5, base_delay=1.0, max_delay=60.0)

    # In a consumer loop:
    for attempt in policy:
        try:
            process_message(message)
            policy.reset()  # success — reset backoff
            break
        except TransientError:
            policy.wait()   # sleep with backoff + jitter
"""
import time
import random
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("retry")


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""
    def __init__(self, attempts: int, last_error: Optional[Exception] = None):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Retry exhausted after {attempts} attempts")


class RetryPolicy:
    """
    Exponential backoff with full jitter (AWS-recommended algorithm).

    delay = min(max_delay, base_delay * 2^attempt)
    sleep = random.uniform(0, delay)

    This prevents thundering herd problems when multiple consumers
    retry simultaneously after a service outage.

    Config:
        max_retries:  max retry attempts before giving up (0 = infinite)
        base_delay:   initial delay in seconds (default 1.0)
        max_delay:    maximum delay cap in seconds (default 60.0)
        jitter:       if True, randomize delay (default True)
    """

    def __init__(
        self,
        max_retries: int = 0,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self._attempt = 0

    @property
    def attempt(self) -> int:
        """Current attempt number (0-indexed)."""
        return self._attempt

    def reset(self) -> None:
        """Reset the retry counter after a successful operation."""
        self._attempt = 0

    def get_delay(self) -> float:
        """
        Calculate the next delay using exponential backoff with optional jitter.

        Returns:
            Delay in seconds before the next retry.
        """
        # Exponential backoff: base_delay * 2^attempt, capped at max_delay
        exp_delay = float(min(self.max_delay, self.base_delay * (2 ** self._attempt)))

        if self.jitter:
            # Full jitter: uniform random between 0 and exp_delay
            return random.uniform(0, exp_delay)
        return exp_delay

    def should_retry(self) -> bool:
        """Check if another retry attempt is allowed."""
        if self.max_retries == 0:
            return True  # infinite retries
        return self._attempt < self.max_retries

    def wait(self) -> float:
        """
        Sleep for the calculated backoff delay and increment attempt counter.

        Returns:
            The actual delay (seconds) that was slept.
        """
        delay = self.get_delay()
        self._attempt += 1

        if delay > 0:
            logger.debug(
                f"Retry attempt {self._attempt}: sleeping {delay:.2f}s "
                f"(max_delay={self.max_delay}s)"
            )
            time.sleep(delay)

        return delay

    def execute(
        self,
        func: Callable,
        *args: Any,
        retryable_exceptions: tuple = (Exception,),
        on_retry: Optional[Callable] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Execute a function with automatic retries.

        Args:
            func: The callable to execute
            retryable_exceptions: Tuple of exception types that trigger retry
            on_retry: Optional callback(attempt, exception) called before each retry

        Returns:
            The return value of func

        Raises:
            RetryExhausted: If all retries are exhausted
            Exception: Non-retryable exceptions are raised immediately
        """
        self.reset()
        last_error = None

        while self.should_retry():
            try:
                result = func(*args, **kwargs)
                self.reset()
                return result
            except retryable_exceptions as e:
                last_error = e
                if on_retry:
                    on_retry(self._attempt, e)
                if not self.should_retry():
                    break
                self.wait()

        raise RetryExhausted(self._attempt, last_error)


def create_consumer_retry_policy() -> RetryPolicy:
    """Factory for the standard consumer thread retry policy."""
    return RetryPolicy(
        max_retries=0,    # infinite retries for consumer loops
        base_delay=1.0,   # start at 1 second
        max_delay=30.0,   # cap at 30 seconds
        jitter=True,      # prevent thundering herd
    )
