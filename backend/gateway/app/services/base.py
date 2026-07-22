"""Abstract base class for all RabbitMQ-backed gateway services."""
from __future__ import annotations

from abc import ABC
from typing import Any, Dict, Optional

from app.core.config import GatewayConfig
from app.core.errors import RPCConnectionError, RPCTimeoutError
from app.core.logging_config import ServiceLogger
from app.core.rabbitmq_client import RabbitMQClient


class BaseRPCService(ABC):
    """Shared request helpers for RabbitMQ-backed gateway services."""

    def __init__(
        self,
        rpc_client: RabbitMQClient,
        logger: ServiceLogger,
        config: GatewayConfig,
    ) -> None:
        self.rpc_client = rpc_client
        self.logger = logger
        self.config = config

    async def _send(
        self,
        routing_key: str,
        payload: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a RabbitMQ RPC request with the short timeout by default."""
        request_timeout = timeout if timeout is not None else self.config.short_timeout
        try:
            return await self.rpc_client.send_request(
                routing_key,
                payload,
                timeout=request_timeout,
            )
        except TimeoutError as exc:
            raise RPCTimeoutError("Request timeout") from exc
        except RuntimeError as exc:
            raise RPCConnectionError("RabbitMQ not available") from exc

    async def _send_long(
        self,
        routing_key: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send a RabbitMQ RPC request using the long-operation timeout."""
        return await self._send(
            routing_key,
            payload,
            timeout=self.config.default_timeout,
        )
