"""Shared resilience, observability, and security library for all microservices."""

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpen, CircuitState
from .context import bound_context, clear_context, get_context, set_context, update_context
from .retry import RetryPolicy, RetryExhausted
from .rate_limiter import RateLimiter, RateLimiterMiddleware
from .deduplication import IdempotencyCache
from .dlq import DeadLetterQueue
from .errors import AppError, ErrorCode, ExceptionHandler, ValidationError, NotFoundError
from .logging import ServiceLogger, setup_logging
from .auth import AuthError, AuthIdentity, ROLE_ADMIN, ROLE_SERVICE, ROLE_USER

__all__ = [
    "AppError",
    "AuthError",
    "AuthIdentity",
    "CircuitBreaker",
    "CircuitBreakerOpen",
    "CircuitState",
    "RetryPolicy",
    "RetryExhausted",
    "RateLimiter",
    "RateLimiterMiddleware",
    "ROLE_ADMIN",
    "ROLE_SERVICE",
    "ROLE_USER",
    "IdempotencyCache",
    "DeadLetterQueue",
    "ErrorCode",
    "ExceptionHandler",
    "NotFoundError",
    "ServiceLogger",
    "ValidationError",
    "bound_context",
    "clear_context",
    "get_context",
    "set_context",
    "setup_logging",
    "update_context",
]
