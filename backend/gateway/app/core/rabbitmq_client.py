"""RabbitMQ client facade used by gateway services."""
from __future__ import annotations

import asyncio
import time as _time
from typing import Any, Dict, Optional

from app.core.config import GatewayConfig
from shared.logging import ServiceLogger
from app.core.rpc_client import GatewayRPCClient

try:
    from shared.circuit_breaker import CircuitBreakerRegistry, CircuitBreakerOpen
    _HAS_CIRCUIT_BREAKER = True
except ImportError:
    _HAS_CIRCUIT_BREAKER = False


class RabbitMQClient:
    """Add circuit breaking around the native RabbitMQ RPC client."""

    def __init__(
        self,
        rpc_client: GatewayRPCClient,
        logger: ServiceLogger,
        config: GatewayConfig,
    ) -> None:
        self._rpc_client = rpc_client
        self.logger = logger
        self.config = config
        self._cb_registry = CircuitBreakerRegistry() if _HAS_CIRCUIT_BREAKER else None

    @property
    def circuit_breaker_registry(self) -> Optional["CircuitBreakerRegistry"]:
        return self._cb_registry

    async def send_request(
        self,
        routing_key: str,
        payload: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        cb = self._get_circuit_breaker(routing_key)
        if cb:
            return await self._send_with_circuit_breaker(cb, routing_key, payload, timeout)
        return await self._rpc_client.request(routing_key, payload, timeout=timeout)

    def _get_circuit_breaker(self, routing_key: str):
        if not self._cb_registry:
            return None
        return self._cb_registry.get_or_create(
            routing_key,
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_max_calls=3,
            success_threshold=2,
        )

    async def _send_with_circuit_breaker(
        self, cb, routing_key: str, payload: Dict[str, Any], timeout: float
    ) -> Dict[str, Any]:
        state = cb.state
        if state.value == "open":
            remaining = cb.recovery_timeout - (_time.monotonic() - cb._opened_at)
            self.logger.log(
                "rabbitmq_client:circuit_breaker",
                f"Circuit OPEN for {cb.name}, rejecting request",
                {"remaining_seconds": round(max(0.0, remaining), 1), "routing_key": routing_key},
            )
            raise CircuitBreakerOpen(cb.name, max(0.0, remaining))
        try:
            result = await self._rpc_client.request(routing_key, payload, timeout=timeout)
            cb._on_success()
            return result
        except (TimeoutError, asyncio.TimeoutError):
            cb._on_failure()
            raise
        except Exception:
            cb._on_failure()
            raise

    # No-ops: RabbitMQ reconnects automatically via connect_robust
    def start_consumer(self) -> None:
        pass

    def shutdown(self) -> None:
        pass
