"""Base RabbitMQ handler with shared reply and error helpers."""
import threading
import time
from typing import Any, Dict, Optional, Tuple, Type, Union
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.messaging.interfaces import IProducer
from shared.logging import ServiceLogger
from app.core.config import Settings
from app.core.errors import NotFoundException, ServiceException, TimeoutException, ValidationException
from shared.auth import attach_internal_auth_context


class BaseRabbitMQHandler:
    """
    Abstract base for all message handlers.

    process_request_with_reply runs handle() in "capture mode" so that
    _send_response / _send_error store the reply dict instead of pushing it
    to the broker.  The RabbitMQ consumer base class then publishes the
    returned dict automatically.

    Provides:
    - Common __init__ (producer, logger, config)
    - _send_response  — correlated success reply
    - _send_error     — correlated error reply
    - _fire_and_forget — uncorrelated publish (pipeline notifications)
    - process_request_with_reply — RabbitMQ-compatible entry point
    """

    def __init__(
        self,
        producer: IProducer,
        logger: ServiceLogger,
        config: Settings,
    ) -> None:
        self.producer = producer
        self.logger = logger
        self.config = config
        # Thread-local storage so concurrent threads (run_in_executor) each get
        # their own capture_mode / captured_reply slot, preventing cross-request
        # corruption when a single handler instance is shared across threads.
        self._tls = threading.local()
        # Provider clients such as vLLM may invoke token callbacks from their
        # own worker threads. The FastAPI loop is shared by all handler calls,
        # so keep a non-thread-local reference for cross-thread publications.
        self._event_loop = None

    def normalize_correlated_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Merge typed-envelope payload fields into legacy top-level request fields."""
        normalized = dict(message)
        payload = message.get("payload")
        if isinstance(payload, dict):
            for key, value in payload.items():
                normalized.setdefault(key, value)
        return normalized

    def _is_typed_caller(self, message: Dict[str, Any]) -> bool:
        """Return whether the request carries typed gateway reply metadata."""
        return all(
            message.get(field)
            for field in ("reply_to", "request_id", "trace_id", "correlation_id", "action")
        )

    # ------------------------------------------------------------------
    # Correlated reply helpers (gateway is blocking-wait for these)
    # ------------------------------------------------------------------

    def _send_response(self, request_or_correlation_id: Union[str, Dict[str, Any]], data: Dict[str, Any]) -> None:
        """Send a success reply using typed or legacy correlated response format.

        In capture mode (used by process_request_with_reply) the reply dict is
        stored in self._captured_reply instead of being published to the broker.
        """
        _topic, message = self._build_correlated_reply(request_or_correlation_id, data=data)
        if getattr(self._tls, "capture_mode", False):
            self._tls.captured_reply = message
        else:
            self.producer.send(_topic, message)
            self.producer.flush()

    def _send_error(
        self,
        request_or_correlation_id: Union[str, Dict[str, Any]],
        message: str,
        error_code: str = "error",
        status_code: Optional[int] = None,
    ) -> None:
        """Send an error reply using typed or legacy correlated response format.

        In capture mode (used by process_request_with_reply) the reply dict is
        stored in self._captured_reply instead of being published to the broker.

        Args:
            request_or_correlation_id: Original request dict or legacy correlation id.
            message:        Human-readable description of what went wrong.
            error_code:     Snake_case machine-readable error tag (e.g. ``schema_invalid``).
        """
        _topic, payload = self._build_correlated_reply(
            request_or_correlation_id,
            data={},
            success=False,
            error={"message": message, "code": error_code, "status_code": status_code},
        )
        if getattr(self._tls, "capture_mode", False):
            self._tls.captured_reply = payload
        else:
            self.producer.send(_topic, payload)
            self.producer.flush()

    def _send_exception(self, request_or_correlation_id: Union[str, Dict[str, Any]], exception: Exception) -> None:
        """Send an error reply with status metadata that gateway can map."""
        message = str(exception)
        error_code = "error"
        status_code = 500

        if isinstance(exception, ValidationException):
            error_code = "validation_error"
            status_code = 400
        elif isinstance(exception, NotFoundException):
            error_code = "not_found"
            status_code = 404
        elif isinstance(exception, TimeoutException):
            error_code = "timeout"
            status_code = 504
        elif isinstance(exception, ServiceException):
            error_code = "service_unavailable"
            status_code = 503

        self._send_error(
            request_or_correlation_id,
            message,
            error_code=error_code,
            status_code=status_code,
        )

    def _build_correlated_reply(
        self,
        request_or_correlation_id: Union[str, Dict[str, Any]],
        data: Dict[str, Any],
        success: bool = True,
        error: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Build a typed or legacy correlated reply for gateway-facing lanes."""
        if isinstance(request_or_correlation_id, dict):
            request = request_or_correlation_id
            if self._is_typed_caller(request):
                return request["reply_to"], {
                    "message_id": uuid4().hex,
                    "message_type": "reply",
                    "action": request["action"],
                    "source_service": self.config.service_name,
                    "target_service": request.get("source_service", "gateway"),
                    "request_id": request["request_id"],
                    "trace_id": request["trace_id"],
                    "correlation_id": request["correlation_id"],
                    "success": success,
                    "payload": data,
                    "error": error,
                    "timestamp": int(time.time() * 1000),
                }
            correlation_id = request.get("correlation_id", "")
        else:
            correlation_id = request_or_correlation_id

        if success:
            return "", {"correlation_id": correlation_id, "data": data}

        message = error["message"] if error else "Unknown error"
        error_code = error["code"] if error else "error"
        return "", {
            "correlation_id": correlation_id,
            "data": {"status": "error", "message": message, "error_code": error_code},
        }

    # ------------------------------------------------------------------
    # Schema validation helper
    # ------------------------------------------------------------------

    def _validate(
        self,
        payload: Dict[str, Any],
        schema_class: Type[BaseModel],
    ) -> Tuple[Optional[BaseModel], Optional[str]]:
        """Validate *payload* against *schema_class*.

        Returns ``(model, None)`` on success or ``(None, error_message)`` on
        validation failure.  The caller is responsible for sending an error
        response when ``error_message`` is not None.
        """
        try:
            return schema_class(**payload), None
        except ValidationError as exc:
            return None, f"Invalid request schema: {exc}"

    # ------------------------------------------------------------------
    # Fire-and-forget helper (pipeline updates, no caller waiting)
    # ------------------------------------------------------------------

    def _fire_and_forget(self, routing_key: str, message: Dict[str, Any]) -> None:
        """
        Publish a message to the RabbitMQ exchange (fire-and-forget).

        Use for pipeline notifications (summary/metadata/question updates to the
        files service) where no caller is blocking on the response.

        This method is called from a thread executor, so it uses
        run_coroutine_threadsafe to schedule the async publish on the event loop
        that was stored in self._loop by process_request_with_reply.
        """
        import asyncio
        loop = getattr(self._tls, "loop", None) or self._event_loop
        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.producer.publish(routing_key, attach_internal_auth_context(message)), loop
            )
            try:
                future.result(timeout=10)
            except Exception:
                self.logger.log(
                    "handler:fire_and_forget",
                    "Failed to publish fire-and-forget message",
                    {"routing_key": routing_key},
                    hypothesis_id="E",
                )
        else:
            self.logger.log(
                "handler:fire_and_forget",
                "No event loop available for fire-and-forget publish",
                {"routing_key": routing_key},
                hypothesis_id="W",
            )

    # ------------------------------------------------------------------
    # RabbitMQ-compatible entry point
    # ------------------------------------------------------------------

    def process_request_with_reply(
        self,
        body: Dict[str, Any],
        reply_to: str,
        correlation_id: str,
        event_loop=None,
    ) -> Optional[Dict[str, Any]]:
        """Sync entry point for RabbitMQ consumer thread-executor integration.

        Injects reply_to / correlation_id into the message body, runs handle()
        in capture mode so that _send_response / _send_error store the reply
        dict rather than pushing it to a broker, and returns that dict.

        For fire-and-forget handlers that never call _send_response the method
        returns None (the RabbitMQ consumer then sends no reply).
        """
        import asyncio
        # Capture the running event loop in thread-local storage so
        # _fire_and_forget can schedule async publishes from within this thread
        # without interfering with other concurrent threads.
        if event_loop is not None:
            self._tls.loop = event_loop
            self._event_loop = event_loop
        else:
            try:
                self._tls.loop = asyncio.get_running_loop()
                self._event_loop = self._tls.loop
            except RuntimeError:
                self._tls.loop = None

        self._tls.capture_mode = True
        self._tls.captured_reply = None
        body = dict(body)
        body.setdefault("reply_to", reply_to)
        body.setdefault("correlation_id", correlation_id)
        try:
            self.handle(body)
        finally:
            self._tls.capture_mode = False

        return self._tls.captured_reply
