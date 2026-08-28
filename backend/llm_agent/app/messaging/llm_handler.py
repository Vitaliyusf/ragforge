"""Typed LLM text-generation handler."""
import asyncio
import time
from contextvars import copy_context
from typing import Any, Dict
from uuid import uuid4

from pydantic import ValidationError

from app.messaging.base_handler import BaseRabbitMQHandler
from app.messaging.interfaces import IProducer
from app.core.config import Settings
from shared.logging import ServiceLogger
from app.core.safety import sanitize_debug_text
from app.schemas.llm import (
    ErrorEntry,
    ModelExecutionReplyMessage,
    ModelExecutionRequestMessage,
    ModelExecutionResponsePayload,
    ModelExecutionStreamEventMessage,
    ModelExecutionStreamPayload,
    SharedMessageError,
    TraceInfo,
    UsageInfo,
    validate_model_execution_request_message,
)
from app.services.llm_service import LLMService
from shared.auth import attach_internal_auth_context


class LLMHandler(BaseRabbitMQHandler):
    """Handle typed model-execution requests for llm_agent."""

    def __init__(
        self,
        producer: IProducer,
        llm_service: LLMService,
        logger: ServiceLogger,
        config: Settings,
    ) -> None:
        super().__init__(producer, logger, config)
        self.llm_service = llm_service

    def handle(self, message: Dict[str, Any]) -> None:
        try:
            request = validate_model_execution_request_message(message)
        except ValidationError as exc:
            self.logger.log(
                "rabbitmq:llm",
                "Typed request validation failed",
                {
                    "request_id": message.get("request_id"),
                    "error": sanitize_debug_text(str(exc), self.config.debug_max_field_length),
                },
                hypothesis_id="E",
            )
            self._publish_reply(self._build_validation_error_reply(message, str(exc)))
            return

        self.logger.log(
            "rabbitmq:llm",
            "Processing typed LLM request",
            {
                "request_type": request.payload.request_type,
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "correlation_id": request.correlation_id,
                "model": request.payload.model,
                "stream_to": request.stream_to,
            },
        )

        stream_context = copy_context()

        def publish_stream(payload: ModelExecutionStreamPayload) -> None:
            # vLLM invokes token callbacks from its own executor. Explicitly
            # restore the authenticated request context before signing each
            # stream envelope.
            stream_context.copy().run(self._publish_stream_event, request, payload)

        reply_payload = self.llm_service.execute(request, publish_stream)
        self._publish_reply(self._build_reply_message(request, reply_payload))

    def _publish_reply(self, reply: ModelExecutionReplyMessage) -> None:
        """Publish the normalized final reply envelope.

        In capture mode (used by process_request_with_reply) the reply dict is
        stored in self._captured_reply so the RabbitMQ consumer base can publish
        it automatically.  Outside capture mode the producer publishes directly.
        """
        reply_dict = reply.model_dump(mode="json")
        if getattr(self._tls, "capture_mode", False):
            self._tls.captured_reply = reply_dict
            return

        # Fallback: async publish via run_coroutine_threadsafe
        loop = self._event_loop or getattr(self._tls, "loop", None)
        reply_to = reply.reply_to or ""
        correlation_id = reply.correlation_id or ""
        if loop is not None and loop.is_running() and reply_to:
            future = asyncio.run_coroutine_threadsafe(
                self.producer.reply(reply_to, correlation_id, reply_dict), loop
            )
            try:
                future.result(timeout=60)
            except Exception:
                self.logger.log("handler:llm", "Failed to publish reply", {"reply_to": reply_to}, hypothesis_id="E")

    def _publish_stream_event(
        self,
        request: ModelExecutionRequestMessage,
        payload: ModelExecutionStreamPayload,
    ) -> None:
        """Publish a streaming token/error/done event via the RabbitMQ exchange."""
        if not request.stream_to:
            return

        event = ModelExecutionStreamEventMessage(
            message_id=self._new_message_id(),
            message_type="stream_event",
            action="answer_generation",
            source_service=self.config.service_name,
            target_service=request.source_service,
            request_id=request.request_id,
            trace_id=request.trace_id,
            correlation_id=request.correlation_id,
            stream_to=request.stream_to,
            timestamp=self._now_ms(),
            payload=payload,
        )
        loop = self._event_loop or getattr(self._tls, "loop", None)
        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.producer.publish(
                    request.stream_to,
                    attach_internal_auth_context(event.model_dump(mode="json")),
                ), loop
            )
            try:
                future.result(timeout=10)
            except Exception:
                self.logger.log("handler:llm", "Failed to publish stream event", {}, hypothesis_id="W")

    def _build_validation_error_reply(
        self,
        message: Dict[str, Any],
        error: str,
    ) -> ModelExecutionReplyMessage:
        """Build a normalized error reply even when inbound validation fails."""
        payload = ModelExecutionResponsePayload(
            request_type=str(message.get("action") or message.get("request_type") or "unknown"),
            status="error",
            raw_prompt="",
            system_prompt="",
            visible_reasoning_steps=["Request validation failed"],
            raw_output="",
            usage=UsageInfo(provider=self.config.llm_implementation),
            # The request never reached a provider, so there is no finish
            # reason to report — and the failure is this service's inbound
            # contract, not the model's.
            provider_finish_reason="unknown",
            application_status="invalid_request",
            latency_ms=0,
            model=str(message.get("payload", {}).get("model", "")),
            prompt_version=str(message.get("payload", {}).get("prompt_version", "")),
            trace=TraceInfo(trace_id=str(message.get("trace_id", ""))),
            errors=[
                ErrorEntry(
                    code="invalid_request",
                    message=f"Invalid request schema: {sanitize_debug_text(error, self.config.debug_max_field_length)}",
                )
            ],
        )
        return ModelExecutionReplyMessage(
            message_id=self._new_message_id(),
            message_type="reply",
            action=str(message.get("action") or message.get("request_type") or "unknown"),
            source_service=self.config.service_name,
            target_service=str(message.get("source_service", "")),
            request_id=str(message.get("request_id", "")),
            trace_id=str(message.get("trace_id", "")),
            correlation_id=str(message.get("correlation_id", "")),
            reply_to=message.get("reply_to"),
            timestamp=self._now_ms(),
            success=False,
            payload=payload,
            error=SharedMessageError(
                code="invalid_request",
                message=payload.errors[0].message,
            ),
        )

    def _build_reply_message(
        self,
        request: ModelExecutionRequestMessage,
        payload: ModelExecutionResponsePayload,
    ) -> ModelExecutionReplyMessage:
        """Wrap the normalized execution payload in the shared reply envelope."""
        error = None
        if payload.status != "success" and payload.errors:
            error = SharedMessageError(
                code=payload.errors[0].code,
                message=payload.errors[0].message,
            )

        return ModelExecutionReplyMessage(
            message_id=self._new_message_id(),
            message_type="reply",
            action=request.action,
            source_service=self.config.service_name,
            target_service=request.source_service,
            request_id=request.request_id,
            trace_id=request.trace_id,
            correlation_id=request.correlation_id,
            reply_to=request.reply_to,
            timestamp=self._now_ms(),
            success=payload.status == "success",
            payload=payload,
            error=error,
        )

    @staticmethod
    def _new_message_id() -> str:
        return uuid4().hex

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
