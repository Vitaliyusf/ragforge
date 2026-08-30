"""Typed LLM execution service."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from app.core.config import Settings
from app.core.errors import (
    ServiceException,
    StreamingNotSupportedException,
    TimeoutException,
)
from app.core.safety import sanitize_debug_text
from app.core.tracing import ExecutionTracer
from app.llm.interfaces import ILLMClient, LLMInvocation
from app.llm.prompt_registry import PromptRegistry
from app.schemas.llm import (
    ErrorEntry,
    ModelExecutionRequestMessage,
    ModelExecutionResponsePayload,
    ModelExecutionStreamPayload,
    TraceInfo,
    UsageInfo,
)
from app.services.base import BaseService
from app.services.execution_pipeline import ExecutionPipeline
from app.services.text_window import ContextWindowResolver
from shared.logging import ServiceLogger
from shared.metrics import METRICS
from shared.schema_provenance import canonical_schema_sha256


StreamPublisher = Callable[[ModelExecutionStreamPayload], None]

_BOUNDED_FINISH_REASONS = frozenset(
    {"completed", "stop", "length", "content_filter", "tool_calls", "cancelled"}
)

# No provider response was received at all. Distinct from `other`, which means
# the provider answered with a finish reason outside the bounded set.
FINISH_REASON_UNKNOWN = "unknown"


def provider_finish_reason(value: Optional[str]) -> str:
    """Map a provider-controlled finish reason onto a bounded label.

    Application state is deliberately not an input here. A truncated response
    the parser then rejected still finished on ``length``, and collapsing that
    into ``error`` destroys the only evidence that says the output ceiling —
    not the model or the prompt — is what broke the call.
    """
    if value is None:
        return FINISH_REASON_UNKNOWN
    normalized = str(value).strip().lower()
    if not normalized:
        return FINISH_REASON_UNKNOWN
    return normalized if normalized in _BOUNDED_FINISH_REASONS else "other"


def _metric_finish_reason(value: Optional[str], *, errored: bool) -> str:
    """Legacy metric label: provider reason, collapsed to ``error`` on failure.

    Kept only so `ragapp_llm_finish_reasons_total` keeps the meaning existing
    dashboards were built against. New readers use
    `ragapp_llm_provider_finish_reasons_total`.
    """
    if errored:
        return "error"
    return provider_finish_reason(value)


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
        self.context_window = ContextWindowResolver(llm_client, config, logger)
        self.pipeline = ExecutionPipeline(
            llm_client,
            config,
            self.prompt_registry,
            self.context_window,
            logger,
        )

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
            return str(result.raw_output)
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
        # None until the provider actually answers. A fabricated `completed`
        # here would claim a finish reason for a call that never reached the
        # provider at all.
        raw_provider_finish_reason: Optional[str] = None
        parse_stage: Optional[str] = None
        # Unknown until the request type resolves; never reported as a number
        # the call was not actually made with.
        resolved_max_tokens: Optional[int] = None
        output_schema_sha256: Optional[str] = None
        provider_duration_seconds: Optional[float] = None
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
            plan = self.pipeline.plan(
                request_message,
                streaming_requested=stream_publisher is not None,
            )
            entry = plan.entry
            if entry.structured_output_required:
                output_schema_sha256 = str(
                    canonical_schema_sha256(entry.output_model.model_json_schema())
                )
            resolved_prompt_version = plan.prompt_version
            resolved_model = plan.model
            resolved_max_tokens = plan.max_tokens
            trace.add_metadata(
                self.pipeline.build_trace_metadata(
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
                rendered = self.pipeline.render(request_message, plan)
                system_prompt = rendered.system_prompt
                raw_prompt = rendered.raw_prompt
                span.finish(
                    outputs={
                        "system_prompt_length": len(system_prompt),
                        "raw_prompt_length": len(raw_prompt),
                    }
                )

            visible_reasoning_steps.append(f"Rendered {resolved_prompt_version}")

            can_stream = plan.can_stream

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

            with trace.span(
                "model_invoke",
                inputs={"model": resolved_model, "streaming": can_stream},
                metadata={"provider": self.config.llm_implementation, "timeout": plan.timeout},
            ) as span:
                provider_started_at = time.perf_counter()
                try:
                    evidence = self.pipeline.invoke(
                        request_message,
                        plan,
                        rendered,
                        on_token if can_stream else None,
                    )
                finally:
                    provider_duration_seconds = time.perf_counter() - provider_started_at
                generation = evidence.generation
                raw_output = generation.raw_output or ""
                finish_reason = generation.finish_reason or "completed"
                raw_provider_finish_reason = finish_reason
                usage = self.pipeline.normalize_usage(generation.usage)
                span.finish(
                    outputs={
                        "finish_reason": finish_reason,
                        "output_length": len(raw_output),
                    }
                )

            visible_reasoning_steps.append(f"Invoked model {resolved_model}")
        except StreamingNotSupportedException as exc:
            status = "error"
            errors.append(self.pipeline.error_entry("streaming_not_supported", str(exc)))
            visible_reasoning_steps.append("Streaming was not supported by the active provider")
            self._publish_stream_error(stream_publisher, "streaming_not_supported", str(exc))
            trace.finish(outputs={"status": status, "error_codes": [err.code for err in errors]}, error=exc)
        except Exception as exc:
            status = "error"
            # A provider/inference failure and a local failure before the call
            # are different diagnoses: one points at the model server, the
            # other at this service.
            error_code = self.pipeline.provider_failure_code(
                exc, provider_attempted=provider_duration_seconds is not None
            )
            errors.append(self.pipeline.error_entry(error_code, str(exc)))
            visible_reasoning_steps.append("Execution failed")
            self._publish_stream_error(stream_publisher, error_code, str(exc))
            trace.finish(outputs={"status": status, "error_codes": [err.code for err in errors]}, error=exc)
        else:
            try:
                with trace.span(
                    "structured_parse",
                    inputs={"request_type": request.request_type},
                    metadata={"structured_output_required": entry.structured_output_required},
                ) as span:
                    try:
                        decoded = self.pipeline.decode(raw_output, request_message, plan)
                        parsed_payload = decoded.payload
                        structured_output_debug = decoded.debug
                    except Exception as exc:
                        parse_stage = "parse"
                        self.pipeline.log_structured_output_failure(
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
                        parsed_payload = self.pipeline.finalize_payload(
                            request_message=request_message,
                            parsed_payload=parsed_payload,
                            resolved_model=resolved_model,
                        )
                        parsed_output = self.pipeline.validate(plan, parsed_payload)
                    except Exception as exc:
                        parse_stage = "validation"
                        self.pipeline.log_structured_output_failure(
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
                    visible_reasoning_steps.extend(
                        self.pipeline.structured_output_debug_steps(structured_output_debug)
                    )
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
                    "validation_error"
                    if entry.structured_output_required and parse_stage == "validation"
                    else (
                        "structured_output_invalid"
                        if entry.structured_output_required
                        else "execution_error"
                    )
                )
                if error_code == "structured_output_invalid" and parse_stage is None:
                    # The output was rejected somewhere other than the two
                    # instrumented stages. `unknown` is the honest label.
                    parse_stage = "unknown"
                errors.append(self.pipeline.error_entry(error_code, str(exc)))
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

        bounded_finish_reason = provider_finish_reason(raw_provider_finish_reason)
        self.pipeline.record_telemetry(
            METRICS,
            config=self.config,
            request_type=request.request_type,
            model=resolved_model,
            latency_seconds=latency_ms / 1000,
            provider_duration_seconds=provider_duration_seconds,
            usage=usage,
            error_code=(errors[0].code if errors else "unknown") if status == "error" else None,
            legacy_finish_reason=_metric_finish_reason(
                raw_provider_finish_reason,
                errored=status == "error",
            ),
            provider_finish_reason=bounded_finish_reason,
        )

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
            # Provider evidence, kept whole. `application_status` says what
            # this service made of the response; neither field overwrites the
            # other.
            provider_finish_reason=bounded_finish_reason,
            application_status=errors[0].code if (status == "error" and errors) else status,
            parse_stage=parse_stage,
            max_tokens=resolved_max_tokens,
            latency_ms=latency_ms,
            model=resolved_model,
            prompt_version=resolved_prompt_version,
            output_schema_sha256=output_schema_sha256,
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
