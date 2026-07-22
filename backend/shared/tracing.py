"""Optional OpenTelemetry tracing helpers for shared/backend code.

The helper initializes an OTLP exporter when OpenTelemetry dependencies are
available and otherwise falls back to no-op tracing. Its context propagation
helpers serialize trace identifiers into regular message dictionaries via
`trace_id`, `span_id`, and `trace_flags`.
"""
import logging
from typing import Dict, Any, Iterator, Optional
from contextlib import contextmanager

logger = logging.getLogger("tracing")

# Lazy imports to handle missing opentelemetry gracefully
_tracer = None
_initialized = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.trace.propagation import get_current_span
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


def init_tracing(
    service_name: str,
    otlp_endpoint: str = "http://jaeger:4317",
) -> None:
    """
    Initialize OpenTelemetry tracing for one service process.

    Args:
        service_name: Service name recorded in OpenTelemetry resources.
        otlp_endpoint: OTLP gRPC endpoint for the exporter.

    Side effects:
        Configures a global tracer provider once per process and logs a warning
        when OpenTelemetry dependencies or the exporter endpoint are unavailable.
    """
    global _tracer, _initialized

    if not _HAS_OTEL:
        logger.warning(
            f"OpenTelemetry not installed for {service_name}. "
            "Install with: pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-exporter-otlp-proto-grpc"
        )
        _initialized = True
        return

    if _initialized:
        return

    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "ragapp",
        "deployment.environment": "development",
    })

    provider = TracerProvider(resource=resource)

    try:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        logger.info(f"Tracing initialized for {service_name} -> {otlp_endpoint}")
    except Exception as e:
        logger.warning(f"Failed to connect to Jaeger at {otlp_endpoint}: {e}")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    _initialized = True


def get_tracer() -> Any:
    """Return the configured tracer, or a no-op-compatible fallback tracer."""
    if _tracer:
        return _tracer
    if _HAS_OTEL:
        return trace.get_tracer("ragapp-fallback")
    return _NoOpTracer()


def inject_trace_context() -> Dict[str, str]:
    """
    Serialize the current span context into plain message fields.

    Returns:
        A dictionary containing `trace_id`, `span_id`, and `trace_flags` when a
        valid OpenTelemetry span is active. Returns an empty dict otherwise.
    """
    if not _HAS_OTEL:
        return {}

    span = get_current_span()
    ctx = span.get_span_context()

    if not ctx or not ctx.is_valid:
        return {}

    return {
        "trace_id": format(ctx.trace_id, "032x"),
        "span_id": format(ctx.span_id, "016x"),
        "trace_flags": str(ctx.trace_flags),
    }


def extract_trace_context(message: Dict[str, Any]) -> Optional[Any]:
    """
    Rebuild an OpenTelemetry parent context from a message dictionary.

    Args:
        message: Mapping expected to contain `trace_id` and `span_id` fields.

    Returns:
        A parent span context suitable for `trace.set_span_in_context`, or
        `None` when the message does not carry valid trace metadata.
    """
    if not _HAS_OTEL:
        return None

    trace_id_hex = message.get("trace_id")
    span_id_hex = message.get("span_id")

    if not trace_id_hex or not span_id_hex:
        return None

    try:
        trace_id = int(trace_id_hex, 16)
        span_id = int(span_id_hex, 16)
        trace_flags_str = message.get("trace_flags", "1")
        trace_flags = trace.TraceFlags(int(trace_flags_str))

        span_context = trace.SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            is_remote=True,
            trace_flags=trace_flags,
        )

        return trace.set_span_in_context(trace.NonRecordingSpan(span_context))
    except (ValueError, TypeError) as e:
        logger.debug(f"Failed to extract trace context: {e}")
        return None


@contextmanager
def traced_operation(name: str, attributes: Optional[Dict[str, str]] = None) -> Iterator[Any]:
    """
    Wrap one operation in a span when tracing is available.

    Args:
        name: Span name.
        attributes: Optional span attributes coerced to strings.

    Yields:
        The active span object, or a no-op span when tracing is disabled.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        yield span


class _NoOpTracer:
    """Fallback tracer when OpenTelemetry is not installed."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> "_NoOpSpanContext":
        return _NoOpSpanContext()

    def start_span(self, name: str, **kwargs: Any) -> "_NoOpSpan":
        return _NoOpSpan()


class _NoOpSpan:
    """No-op span for when tracing is disabled."""
    def set_attribute(self, key: str, value: Any) -> None: pass
    def set_status(self, status: Any) -> None: pass
    def record_exception(self, exc: BaseException) -> None: pass
    def end(self) -> None: pass
    def get_span_context(self) -> None: return None


class _NoOpSpanContext:
    """Context manager wrapper for no-op spans."""
    def __enter__(self) -> "_NoOpSpan":
        return _NoOpSpan()
    def __exit__(self, *args: Any) -> None:
        pass
