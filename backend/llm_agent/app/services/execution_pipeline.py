"""Cohesive planning, rendering, invocation, decoding, validation, and telemetry."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.core.config import Settings
from app.core.errors import TimeoutException
from app.core.safety import redact_secrets, sanitize_debug_text
from app.llm.interfaces import (
    ILLMClient,
    LLMGenerationResult,
    LLMInvocation,
    LLMUsage,
    ProviderHTTPError,
    ProviderProtocolError,
    ProviderTimeoutError,
)
from app.llm.prompt_registry import PromptRegistry, PromptRegistryEntry, StructuredExtractionResult
from app.schemas.llm import ErrorEntry, ModelExecutionRequestMessage, UsageInfo
from app.services.text_window import ContextWindowResolver, estimate_tokens, truncate_middle
from shared.metrics import traffic_class
from shared.logging import ServiceLogger


@dataclass(frozen=True)
class ExecutionPlan:
    """Resolved immutable choices for one typed execution."""

    entry: PromptRegistryEntry
    model: str
    prompt_version: str
    max_tokens: int
    timeout: float
    can_stream: bool


@dataclass(frozen=True)
class RenderedExecution:
    """Context-window-safe prompt parts."""

    system_prompt: str
    raw_prompt: str


@dataclass(frozen=True)
class InvocationEvidence:
    """Provider result plus measured provider duration."""

    generation: LLMGenerationResult
    duration_seconds: float


@dataclass(frozen=True)
class DecodedOutput:
    """Parsed payload and optional structured extraction evidence."""

    payload: Any
    debug: Optional[Dict[str, Any]]


class ExecutionPipeline:
    """Typed execution stages used by the public ``LLMService`` façade."""

    def __init__(
        self,
        client: ILLMClient,
        config: Settings,
        registry: PromptRegistry,
        context_window: ContextWindowResolver,
        logger: ServiceLogger,
    ) -> None:
        self._client = client
        self._config = config
        self._registry = registry
        self._context_window = context_window
        self._logger = logger

    def plan(
        self,
        request_message: ModelExecutionRequestMessage,
        *,
        streaming_requested: bool,
    ) -> ExecutionPlan:
        request = request_message.payload
        entry = self._registry.resolve(request.request_type, request.prompt_version)
        return ExecutionPlan(
            entry=entry,
            model=request.model or entry.default_model(self._config),
            prompt_version=entry.prompt_version,
            max_tokens=self._config.max_tokens_for_request_type(request.request_type),
            timeout=request.timeout or self._config.llm_timeout,
            can_stream=bool(request_message.stream_to and entry.streaming_allowed and streaming_requested),
        )

    def render(self, request_message: ModelExecutionRequestMessage, plan: ExecutionPlan) -> RenderedExecution:
        rendered = plan.entry.build_prompt(request_message.payload)
        input_budget = self._context_window.input_budget_chars(
            plan.model,
            reserved_tokens=estimate_tokens(rendered.system_prompt),
            output_tokens=plan.max_tokens,
        )
        return RenderedExecution(
            system_prompt=rendered.system_prompt,
            raw_prompt=truncate_middle(rendered.raw_prompt, input_budget),
        )

    def invoke(
        self,
        request_message: ModelExecutionRequestMessage,
        plan: ExecutionPlan,
        rendered: RenderedExecution,
        on_token: Optional[Callable[[str, int], None]],
    ) -> InvocationEvidence:
        request = request_message.payload
        structured = plan.entry.structured_output_required
        invocation = LLMInvocation(
            system_prompt=rendered.system_prompt,
            raw_prompt=rendered.raw_prompt,
            model=plan.model,
            timeout=plan.timeout,
            max_tokens=plan.max_tokens,
            on_token=on_token if plan.can_stream else None,
            metadata={
                "request_type": request.request_type,
                "request_id": request_message.request_id,
                "trace_id": request_message.trace_id,
                "correlation_id": request_message.correlation_id,
                "structured_output_hint": "json_object" if structured else None,
                "structured_output_transport": (
                    self._config.answer_evaluation_structured_output_transport
                    if request.request_type == "answer_evaluation"
                    else "legacy"
                ),
                "structured_output_schema": (
                    plan.entry.output_model.model_json_schema()
                    if request.request_type == "answer_evaluation"
                    and self._config.answer_evaluation_structured_output_transport == "json_schema"
                    else None
                ),
            },
        )
        started_at = time.perf_counter()
        try:
            generation = self._client.generate(invocation)
        finally:
            duration = time.perf_counter() - started_at
        return InvocationEvidence(generation=generation, duration_seconds=duration)

    @staticmethod
    def decode(raw_output: str, request_message: ModelExecutionRequestMessage, plan: ExecutionPlan) -> DecodedOutput:
        parser = plan.entry.parser
        parsed = parser(raw_output, request_message.payload) if plan.entry.parser_accepts_request else parser(raw_output)
        if isinstance(parsed, StructuredExtractionResult):
            return DecodedOutput(payload=parsed.payload, debug=parsed.metadata)
        return DecodedOutput(payload=parsed, debug=None)

    @staticmethod
    def validate(plan: ExecutionPlan, payload: Any) -> Any:
        return plan.entry.output_model.model_validate(payload)

    @staticmethod
    def record_telemetry(
        metrics: Any,
        *,
        config: Settings,
        request_type: str,
        model: str,
        latency_seconds: float,
        provider_duration_seconds: Optional[float],
        usage: UsageInfo,
        error_code: Optional[str],
        legacy_finish_reason: str,
        provider_finish_reason: str,
    ) -> None:
        labels = {
            "service": config.service_name,
            "model": model or "unknown",
            "request_type": request_type,
            "traffic_class": traffic_class(),
        }
        metrics.llm_requests_total.labels(**labels).inc()
        metrics.llm_request_duration.labels(**labels).observe(latency_seconds)
        if provider_duration_seconds is not None:
            metrics.llm_provider_duration.labels(**labels).observe(provider_duration_seconds)
        if error_code is not None:
            metrics.llm_errors_total.labels(**labels, error_type=error_code).inc()
        for direction, token_count in (
            ("input", usage.input_tokens),
            ("output", usage.output_tokens),
            ("total", usage.total_tokens),
        ):
            if token_count is not None:
                metrics.llm_tokens_total.labels(**labels, direction=direction).inc(token_count)
        if usage.output_tokens is not None:
            metrics.llm_output_tokens.labels(
                service=config.service_name,
                request_type=request_type,
                traffic_class=labels["traffic_class"],
            ).observe(usage.output_tokens)
        metrics.llm_finish_reasons_total.labels(
            **labels, finish_reason=legacy_finish_reason
        ).inc()
        metrics.llm_provider_finish_reasons_total.labels(
            **labels, finish_reason=provider_finish_reason
        ).inc()

    @staticmethod
    def provider_failure_code(exc: Exception, *, provider_attempted: bool) -> str:
        if isinstance(exc, ProviderProtocolError):
            return "provider_protocol_error"
        if isinstance(exc, ProviderTimeoutError):
            return "provider_timeout"
        if isinstance(exc, ProviderHTTPError):
            return "provider_http_error"
        if isinstance(exc, (TimeoutError, TimeoutException)):
            return "provider_timeout"
        return "provider_error" if provider_attempted else "execution_error"

    def normalize_usage(self, usage: LLMUsage) -> UsageInfo:
        return UsageInfo(
            provider=usage.provider or self._config.llm_implementation,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )

    def error_entry(self, code: str, message: str) -> ErrorEntry:
        return ErrorEntry(
            code=code,
            message=sanitize_debug_text(redact_secrets(message), self._config.debug_max_field_length),
        )

    def build_trace_metadata(
        self,
        request_message: ModelExecutionRequestMessage,
        resolved_model: str,
        resolved_prompt_version: str,
    ) -> Dict[str, Any]:
        request = request_message.payload
        metadata: Dict[str, Any] = {
            "service": self._config.service_name,
            "request_id": request_message.request_id,
            "trace_id": request_message.trace_id,
            "correlation_id": request_message.correlation_id,
            "request_type": request.request_type,
            "model_name": resolved_model,
            "prompt_version": resolved_prompt_version,
        }
        for field_name in (
            "conversation_id",
            "turn_id",
            "file_id",
            "document_id",
            "graph_run_id",
            "mode",
        ):
            value = request.metadata.get(field_name)
            if value is not None:
                metadata[field_name] = value
        return metadata

    def log_structured_output_failure(
        self,
        request_message: ModelExecutionRequestMessage,
        resolved_model: str,
        resolved_prompt_version: str,
        raw_output: str,
        stage: str,
        detail: str,
        normalized_payload: Optional[Any] = None,
        extraction_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        request_type = request_message.payload.request_type
        data: Dict[str, Any] = {
            "request_type": request_type,
            "request_id": request_message.request_id,
            "trace_id": request_message.trace_id,
            "correlation_id": request_message.correlation_id,
            "model": resolved_model,
            "prompt_version": resolved_prompt_version,
            "parse_stage": stage,
            "validation_stage": "not_started" if stage == "parse" else "failed",
            "raw_output_excerpt": sanitize_debug_text(
                redact_secrets(raw_output), self._config.debug_max_field_length
            ),
            "detail": sanitize_debug_text(redact_secrets(detail), self._config.debug_max_field_length),
        }
        if extraction_metadata:
            data.update(
                payload_count=extraction_metadata.get("payload_count"),
                selected_payload_index=extraction_metadata.get("selected_payload_index"),
                extraction_mode=extraction_metadata.get("extraction_mode"),
            )
        if normalized_payload is not None:
            data["normalized_payload"] = normalized_payload
        self._logger.log(
            "service:llm",
            "Typed structured output handling failed",
            data,
            hypothesis_id="E",
        )

    @staticmethod
    def structured_output_debug_steps(metadata: Dict[str, Any]) -> List[str]:
        debug_blob = {
            "payload_count": metadata.get("payload_count"),
            "selected_payload_index": metadata.get("selected_payload_index"),
            "selection_policy": metadata.get("selection_policy"),
            "extraction_mode": metadata.get("extraction_mode"),
            "candidates": metadata.get("candidates", []),
        }
        return [
            f"Structured output extraction mode: {metadata.get('extraction_mode', 'unknown')}",
            f"Structured output payload count: {metadata.get('payload_count', 0)}",
            f"Structured output selected index: {metadata.get('selected_payload_index')}",
            f"__structured_output_debug__:{json.dumps(debug_blob, ensure_ascii=True)}",
        ]

    @staticmethod
    def finalize_payload(
        request_message: ModelExecutionRequestMessage,
        parsed_payload: Any,
        resolved_model: str,
    ) -> Any:
        if request_message.payload.request_type != "answer_evaluation":
            return parsed_payload
        if not isinstance(parsed_payload, dict):
            raise ValueError("Answer evaluation output must be a JSON object")

        def float_or_none(value: Any) -> Any:
            try:
                return None if value is None else float(value)
            except (TypeError, ValueError):
                return None

        def int_or_none(value: Any) -> Any:
            try:
                return None if value is None else int(value)
            except (TypeError, ValueError):
                return None

        return {
            "review_id": str(parsed_payload.get("review_id") or f"review_{request_message.request_id}"),
            "verdict": str(parsed_payload.get("verdict") or "unknown").strip(),
            "groundedness_score": float_or_none(parsed_payload.get("groundedness_score")),
            "completeness_score": float_or_none(parsed_payload.get("completeness_score")),
            "safety_score": float_or_none(parsed_payload.get("safety_score")),
            "issues": parsed_payload.get("issues") or [],
            "claims": parsed_payload.get("claims") or [],
            "unsupported_claim_count": int_or_none(parsed_payload.get("unsupported_claim_count")),
            "hallucination_verdict": parsed_payload.get("hallucination_verdict"),
            "revision_applied": bool(parsed_payload.get("revision_applied", False)),
            "model_name": resolved_model,
            "created_at": int(time.time() * 1000),
        }
