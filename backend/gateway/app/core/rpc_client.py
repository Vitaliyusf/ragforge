"""Native async RabbitMQ RPC client — replaces GatewayKafkaRequestClient."""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from app.core.config import GatewayConfig
from app.core.correlation import ensure_correlation_ids
from app.core.errors import GatewayError, NotFoundError, ServiceUnavailableError, ValidationError
from shared.logging import ServiceLogger
from app.core.request_context import get_request_context
from app.schemas.common import MessageEnvelope, ReplyEnvelope, MessageType
from shared.auth import identity_from_context
from shared.rabbitmq_rpc import MultiplexedRabbitMQRPCClient


class GatewayRPCClient:
    """Publish requests through one bounded, multiplexed process transport."""

    def __init__(
        self,
        config: GatewayConfig,
        logger: ServiceLogger,
    ) -> None:
        self._url: str = config.rabbitmq_url
        self._exchange_name: str = config.rabbitmq_exchange
        self.logger = logger
        self.config = config
        self._transport = MultiplexedRabbitMQRPCClient(
            self._url,
            self._exchange_name,
            config.service_name,
            max_inflight=getattr(config, "rabbitmq_rpc_max_inflight", 64),
        )

    async def connect(self) -> None:
        """Establish the RabbitMQ connection."""
        await self._transport.connect()

    async def close(self) -> None:
        """Close the RabbitMQ connection."""
        await self._transport.close()

    def is_connected(self) -> bool:
        """Return whether the robust RabbitMQ connection is currently usable."""
        return self._transport.is_connected()

    async def request(
        self,
        routing_key: str,
        payload: Dict[str, Any],
        timeout: float = 30.0,
        target_service: Optional[str] = None,
        message_type: Optional[MessageType] = None,
    ) -> Dict[str, Any]:
        """Publish a typed request envelope and wait for the reply."""
        action = payload.get("action", "request")
        business_payload = {k: v for k, v in payload.items() if k != "action"}
        target_service = target_service or routing_key
        message_type = message_type or self._infer_message_type(action)

        context = get_request_context()
        request_id, trace_id = ensure_correlation_ids(
            context.get("request_id"),
            context.get("trace_id"),
        )
        correlation_id = str(uuid.uuid4())
        identity = identity_from_context()
        envelope = MessageEnvelope(
            message_id=str(uuid.uuid4()),
            message_type=message_type,
            action=action,
            source_service=self.config.service_name,
            target_service=target_service,
            request_id=request_id,
            trace_id=trace_id,
            correlation_id=correlation_id,
            timestamp=int(time.time() * 1000),
            auth_context="pending",
            payload=business_payload,
        )
        envelope_dict = envelope.model_dump(mode="python", exclude_none=True)
        raw_reply = await self._transport.request(
            routing_key,
            envelope_dict,
            timeout=timeout,
            auth_kwargs={
                "ttl_seconds": self.config.internal_auth_ticket_ttl_seconds,
                "identity": identity,
                "secret": self.config.internal_auth_secret,
            },
        )
        self.logger.log(
            "rpc_client:request",
            "RPC request completed",
            {
                "routing_key": routing_key,
                "action": action,
                "target_service": target_service,
                "correlation_id": correlation_id,
            },
        )
        reply = ReplyEnvelope.model_validate(raw_reply)
        if not reply.success:
            self._raise_for_reply_error(reply)
        return reply.payload

    def _infer_message_type(self, action: str) -> MessageType:
        query_prefixes = ("get_", "list_", "fetch_", "search_", "find_")
        query_actions = {"list", "fetch_models", "get_config", "get_generation_params", "get_model_configs"}
        if action.startswith(query_prefixes) or action in query_actions:
            return "query"
        return "command"

    def _raise_for_reply_error(self, reply: ReplyEnvelope) -> None:
        error = reply.error
        message = f"Downstream action '{reply.action}' failed"
        status_code: Optional[int] = None
        if isinstance(error, dict):
            message = (
                error.get("message") or error.get("detail") or error.get("error") or message
            )
            raw_status = error.get("status_code") or error.get("code")
            if isinstance(raw_status, int):
                status_code = raw_status
        elif isinstance(error, str) and error.strip():
            message = error
        if status_code in (400, 422):
            raise ValidationError(message)
        if status_code == 404:
            raise NotFoundError(message)
        if status_code == 503:
            raise ServiceUnavailableError(message)
        raise GatewayError(message, details=reply.payload)
