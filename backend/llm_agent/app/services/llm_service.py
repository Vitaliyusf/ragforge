"""Typed LLM execution service."""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional

from app.core.config import Settings
from app.services.base import BaseService
from app.core.errors import (
    ServiceException,
    StreamingNotSupportedException,
    TimeoutException,
)
from app.core.logging_config import ServiceLogger
from app.core.safety import redact_secrets, sanitize_debug_text
from app.core.tracing import ExecutionTracer
from app.llm.interfaces import ILLMClient, LLMInvocation, LLMUsage
from app.llm.prompt_registry import (
    PromptRegistry,
    STRUCTURED_OUTPUT_DEBUG_PREFIX,
    StructuredExtractionResult,
)
from app.schemas.llm import (
    ErrorEntry,
    ModelExecutionRequestMessage,
    ModelExecutionResponsePayload,
    ModelExecutionStreamPayload,
    TraceInfo,
    UsageInfo,
)
from shared.metrics import METRICS


StreamPublisher = Callable[[ModelExecutionStreamPayload], None]


class LLMService(BaseService):
    """Service for typed LLM prompt execution and legacy text generation."""

    def __init__(
        self,
        llm_client: ILLMClient,
        logger: ServiceLogger,
        config: Settings,
    ):
        self.llm_client = llm_client
        self.logger = logger
        self.config = config
        self.prompt_registry = PromptRegistry(config)
        self.tracer = ExecutionTracer(config)

    def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Generate freeform text for legacy internal callers.

        This path remains available for existing summary/question-generation flows.
        """
        requested_model = model or self.config.default_model or self.config.rag_chat_model
        timeout = timeout or self.config.llm_timeout

        self.logger.log(
            "service:llm",
            "Generating legacy text",
            {"model": requested_model, "prompt_length": len(prompt), "timeout": timeout},
        )

        try:
            result = self.llm_client.generate(
                LLMInvocation(
                    system_prompt="",
                    raw_prompt=prompt,
                    model=requested_model,
                    timeout=timeout,
                )
            )
            return result.raw_output
        except TimeoutError as exc:
            raise TimeoutException(
                f"LLM generation timed out after {timeout}s",
                original_exception=exc,
            )
        except Exception as exc:
            raise ServiceException(
                "Something went wrong while generating the response. Please try again.",
                original_exception=exc,
            )

    def execute(
        self,
        request_message: ModelExecutionRequestMessage,
        stream_publisher: Optional[StreamPublisher] = None,
    ) -> ModelExecutionResponsePayload:
        """Execute one typed request and return the normalized inner reply payload."""
        started_at = time.perf_counter()
        request = request_message.payload
        visible_reasoning_steps: List[str] = []
        system_prompt = ""
        raw_prompt = ""
        raw_output = ""
        parsed_output = None
        structured_output_debug: Optional[Dict[str, Any]] = None
        errors: List[ErrorEntry] = []
        usage = UsageInfo(provider=self.config.llm_implementation)
        finish_reason = "completed"
        token_event_count = 0
        status = "success"
        can_stream = False

        resolved_prompt_version = request.prompt_version or ""
        resolved_model = request.model or self.config.default_model or self.config.rag_chat_model or ""
        trace = self.tracer.start_execution(
            name=f"{request.request_type}.execute",
            trace_id=request_message.trace_id,
            inputs={
                "request_type": request.request_type,
                "request_id": request_message.request_id,
            },
            metadata={
                "service": self.config.service_name,
                "request_type": request.request_type,
                "request_id": request_message.request_id,
                "trace_id": request_message.trace_id,
                "correlation_id": request_message.correlation_id,
            },
        )

        try:
            entry = self.prompt_registry.resolve(request.request_type, request.prompt_version)
            resolved_prompt_version = entry.prompt_version
            resolved_model = request.model or entry.default_model(self.config)
            trace.add_metadata(
                self._build_trace_metadata(
                    request_message=request_message,
                    resolved_model=resolved_model,
                    resolved_prompt_version=resolved_prompt_version,
                )
            )

            with trace.span(
                "prompt_render",
                inputs={"request_type": request.request_type},
                metadata={"prompt_version": resolved_prompt_version},
            ) as span:
                rendered_prompt = entry.build_prompt(request)
                system_prompt = rendered_prompt.system_prompt
                raw_prompt = rendered_prompt.raw_prompt
                span.finish(
                    outputs={
                        "system_prompt_length": len(system_prompt),
                        "raw_prompt_length": len(raw_prompt),
                    }
                )

            visible_reasoning_steps.append(f"Rendered {resolved_prompt_version}")

            can_stream = bool(
                request_message.stream_to and entry.streaming_allowed and stream_publisher
            )

            def on_token(token: str, index: int) -> None:
                nonlocal token_event_count
                token_event_count += 1
                if not can_stream or stream_publisher is None:
                    return
                stream_publisher(
                    ModelExecutionStreamPayload(
                        event_type="llm.token",
                        data={"token": token, "index": index},
                    )
                )

            timeout = request.timeout or self.config.llm_timeout
            invocation = LLMInvocation(
                system_prompt=system_prompt,
                raw_prompt=raw_prompt,
                model=resolved_model,
                timeout=timeout,
                on_token=on_token if can_stream else None,
                metadata={
                    "request_type": request.request_type,
                    "request_id": request_message.request_id,
                    "trace_id": request_message.trace_id,
                    "correlation_id": request_message.correlation_id,
                    "structured_output_hint": (
                        "json_object"
                        if request.request_type in {"answer_evaluation", "content_risk_scan", "memory_extraction"}
                        else None
                    ),
                },
            )

            with trace.span(
                "model_invoke",
                inputs={"model": resolved_model, "streaming": can_stream},
                metadata={"provider": self.config.llm_implementation, "timeout": timeout},
            ) as span:
                generation = self.llm_client.generate(invocation)
                raw_output = generation.raw_output or ""
                finish_reason = generation.finish_reason or "completed"
                usage = self._normalize_usage(generation.usage)
                span.finish(
                    outputs={
                        "finish_reason": finish_reason,
                        "output_length": len(raw_output),
                    }
                )

            visible_reasoning_steps.append(f"Invoked model {resolved_model}")
        except StreamingNotSupportedException as exc:
            status = "error"
            errors.append(self._error_entry("streaming_not_supported", str(exc)))
            visible_reasoning_steps.append("Streaming was not supported by the active provider")
            self._publish_stream_error(stream_publisher, "streaming_not_supported", str(exc))
            trace.finish(outputs={"status": status, "error_codes": [err.code for err in errors]}, error=exc)
        except Exception as exc:
            status = "error"
            errors.append(self._error_entry("execution_error", str(exc)))
            visible_reasoning_steps.append("Execution failed")
            self._publish_stream_error(stream_publisher, "execution_error", str(exc))
            trace.finish(outputs={"status": status, "error_codes": [err.code for err in errors]}, error=exc)
        else:
            try:
                with trace.span(
                    "structured_parse",
                    inputs={"request_type": request.request_type},
                    metadata={"structured_output_required": entry.structured_output_required},
                ) as span:
                    try:
                        parsed_payload = entry.parser(raw_output)
                        if isinstance(parsed_payload, StructuredExtractionResult):
                            structured_output_debug = parsed_payload.metadata
                            parsed_payload = parsed_payload.payload
                    except Exception as exc:
                        self._log_structured_output_failure(
                            request_message=request_message,
                            resolved_model=resolved_model,
                            resolved_prompt_version=resolved_prompt_version,
                            raw_output=raw_output,
                            stage="parse",
                            detail=str(exc),
                            extraction_metadata=getattr(exc, "metadata", None),
                        )
                        raise ValueError(f"Structured output parse failed: {str(exc)}") from exc
                    span.finish(outputs={"parser": entry.output_model.__name__})

                with trace.span(
                    "validation",
                    inputs={"output_model": entry.output_model.__name__},
                    metadata=None,
                ) as span:
                    try:
                        parsed_payload = self._finalize_parsed_payload(
                            request_message=request_message,
                            parsed_payload=parsed_payload,
                            resolved_model=resolved_model,
                        )
                        parsed_output = entry.output_model.model_validate(parsed_payload)
                    except Exception as exc:
                        self._log_structured_output_failure(
                            request_message=request_message,
                            resolved_model=resolved_model,
                            resolved_prompt_version=resolved_prompt_version,
                            raw_output=raw_output,
                            stage="validation",
                            detail=str(exc),
                            normalized_payload=parsed_payload if "parsed_payload" in locals() else None,
                            extraction_metadata=structured_output_debug,
                        )
                        raise ValueError(f"Structured output validation failed: {str(exc)}") from exc
                    span.finish(outputs={"validated": True})

                visible_reasoning_steps.append("Validated parsed output")
                if structured_output_debug:
                    visible_reasoning_steps.extend(self._build_structured_output_debug_steps(structured_output_debug))
                    if structured_output_debug.get("payload_count", 0) > 1:
                        self.logger.log(
                            "service:llm",
                            "Structured output multi-payload recovery succeeded",
                            {
                                "request_type": request.request_type,
                                "request_id": request_message.request_id,
                                "trace_id": request_message.trace_id,
                                "correlation_id": request_message.correlation_id,
                                "model": resolved_model,
                                "prompt_version": resolved_prompt_version,
                                "payload_count": structured_output_debug.get("payload_count"),
                                "selected_payload_index": structured_output_debug.get("selected_payload_index"),
                                "extraction_mode": structured_output_debug.get("extraction_mode"),
                            },
                        )

                if can_stream and stream_publisher is not None:
                    stream_publisher(
                        ModelExecutionStreamPayload(
                            event_type="llm.done",
                            data={
                                "finish_reason": finish_reason,
                                "token_count": token_event_count,
                            },
                        )
                    )
            except Exception as exc:
                status = "error"
                error_code = (
                    "structured_output_invalid"
                    if entry.structured_output_required
                    else "execution_error"
                )
                errors.append(self._error_entry(error_code, str(exc)))
                visible_reasoning_steps.append(
                    "Structured output validation failed"
                    if error_code == "structured_output_invalid"
                    else "Execution failed"
                )
                self._publish_stream_error(stream_publisher, error_code, str(exc))
                trace.finish(outputs={"status": status, "error_codes": [err.code for err in errors]}, error=exc)
            else:
                trace.finish(outputs={"status": status, "finish_reason": finish_reason})

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        trace_snapshot = trace.snapshot()

        metric_model = resolved_model or "unknown"
        METRICS.llm_requests_total.labels(
            service=self.config.service_name,
            model=metric_model,
            action=request.request_type,
        ).inc()
        METRICS.llm_request_duration.labels(
            service=self.config.service_name,
            model=metric_model,
        ).observe(latency_ms / 1000)
        if status == "error":
            METRICS.llm_errors_total.labels(
                service=self.config.service_name,
                model=metric_model,
                error_type=errors[0].code if errors else "unknown",
            ).inc()
        # Skip None rather than coercing to 0, so a provider that reports no
        # usage does not look like zero-cost traffic.
        for direction, token_count in (
            ("input", usage.input_tokens),
            ("output", usage.output_tokens),
        ):
            if token_count is not None:
                METRICS.llm_tokens_total.labels(
                    service=self.config.service_name,
                    model=metric_model,
                    direction=direction,
                ).inc(token_count)

        response_payload = ModelExecutionResponsePayload(
            request_type=request.request_type,
            status=status,
            raw_prompt=sanitize_debug_text(raw_prompt, self.config.debug_max_field_length),
            system_prompt=sanitize_debug_text(system_prompt, self.config.debug_max_field_length),
            visible_reasoning_steps=(
                visible_reasoning_steps if request.debug.include_visible_reasoning_steps else []
            ),
            raw_output=sanitize_debug_text(raw_output, self.config.debug_max_field_length),
            parsed_output=parsed_output,
            usage=usage,
            latency_ms=latency_ms,
            model=resolved_model,
            prompt_version=resolved_prompt_version,
            trace=TraceInfo(
                trace_id=trace_snapshot.trace_id,
                langsmith_run_id=trace_snapshot.langsmith_run_id,
                langsmith_trace_url=trace_snapshot.langsmith_trace_url,
            ),
            errors=errors,
        )

        self.logger.log(
            "service:llm",
            "Typed execution completed",
            {
                "request_type": request.request_type,
                "request_id": request_message.request_id,
                "status": status,
                "model": resolved_model,
                "prompt_version": resolved_prompt_version,
                "latency_ms": latency_ms,
                "error_codes": [error.code for error in errors],
            },
            hypothesis_id="E" if status == "error" else "A",
        )
        return response_payload

    def _publish_stream_error(
        self,
        stream_publisher: Optional[StreamPublisher],
        error_code: str,
        message: str,
    ) -> None:
        if stream_publisher is None:
            return

        stream_publisher(
            ModelExecutionStreamPayload(
                event_type="llm.error",
                data={
                    "code": error_code,
                    "message": sanitize_debug_text(message, self.config.debug_max_field_length),
                },
            )
        )

    def _normalize_usage(self, usage: LLMUsage) -> UsageInfo:
        return UsageInfo(
            provider=usage.provider or self.config.llm_implementation,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )

    def _error_entry(self, code: str, message: str) -> ErrorEntry:
        return ErrorEntry(
            code=code,
            message=sanitize_debug_text(redact_secrets(message), self.config.debug_max_field_length),
        )

    def _build_trace_metadata(
        self,
        request_message: ModelExecutionRequestMessage,
        resolved_model: str,
        resolved_prompt_version: str,
    ) -> Dict[str, Any]:
        request = request_message.payload
        metadata: Dict[str, Any] = {
            "service": self.config.service_name,
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

    def _log_structured_output_failure(
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
        if request_type not in {"answer_evaluation", "content_risk_scan"}:
            return

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
                redact_secrets(raw_output),
                self.config.debug_max_field_length,
            ),
            "detail": sanitize_debug_text(
                redact_secrets(detail),
                self.config.debug_max_field_length,
            ),
        }
        if extraction_metadata:
            data["payload_count"] = extraction_metadata.get("payload_count")
            data["selected_payload_index"] = extraction_metadata.get("selected_payload_index")
            data["extraction_mode"] = extraction_metadata.get("extraction_mode")
        if normalized_payload is not None:
            data["normalized_payload"] = normalized_payload

        self.logger.log(
            "service:llm",
            "Typed structured output handling failed",
            data,
            hypothesis_id="E",
        )

    def _build_structured_output_debug_steps(self, metadata: Dict[str, Any]) -> List[str]:
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
            f"{STRUCTURED_OUTPUT_DEBUG_PREFIX}{json.dumps(debug_blob, ensure_ascii=True)}",
        ]

    def _finalize_parsed_payload(
        self,
        request_message: ModelExecutionRequestMessage,
        parsed_payload: Any,
        resolved_model: str,
    ) -> Any:
        request = request_message.payload
        if request.request_type == "content_risk_scan":
            return parsed_payload

        if request.request_type != "answer_evaluation":
            return parsed_payload

        if not isinstance(parsed_payload, dict):
            raise ValueError("Answer evaluation output must be a JSON object")

        verdict_raw = parsed_payload.get("verdict")
        verdict = str(verdict_raw).strip() if verdict_raw is not None else "unknown"

        def _to_float_or_none(v: Any) -> Any:
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return {
            "review_id": str(parsed_payload.get("review_id") or f"review_{request_message.request_id}"),
            "verdict": verdict,
            "groundedness_score": _to_float_or_none(parsed_payload.get("groundedness_score")),
            "completeness_score": _to_float_or_none(parsed_payload.get("completeness_score")),
            "safety_score": _to_float_or_none(parsed_payload.get("safety_score")),
            "issues": parsed_payload.get("issues") or [],
            "revision_applied": bool(parsed_payload.get("revision_applied", False)),
            "model_name": resolved_model,
            "created_at": int(time.time() * 1000),
        }
