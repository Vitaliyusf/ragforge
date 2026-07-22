"""Canonical structured logger for backend services."""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional, cast

from .context import get_context


REDACTED = "<redacted>"
_SECRET_KEYS = {
    "authorization",
    "auth_context",
    "cookie",
    "set_cookie",
    "ticket",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "x-api-key",
    "x-csrf-token",
    "x-internal-auth",
}

_PRIVATE_CONTENT_KEYS = {
    "answer",
    "content",
    "content_b64",
    "extracted_text",
    "prompt",
    "question",
    "recent_messages",
    "sanitized_text",
    "system_prompt",
    "user_message",
}
_NORMALIZED_SECRET_KEYS = frozenset(item.replace("-", "_") for item in _SECRET_KEYS)


def _default_log_dir() -> str:
    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    return os.getenv("LOG_DIR", str(repo_root / "logs"))


def _is_secret_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    return (
        normalized in _NORMALIZED_SECRET_KEYS
        or normalized in _PRIVATE_CONTENT_KEYS
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
    )


def redact_value(value: Any, *, key: Optional[str] = None) -> Any:
    """Recursively redact sensitive values while preserving useful structure."""
    if key and _is_secret_key(key):
        return REDACTED

    if isinstance(value, (bytes, bytearray)):
        return f"<redacted-bytes:{len(value)}>"

    if isinstance(value, Mapping):
        return {str(k): redact_value(v, key=str(k)) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [redact_value(item) for item in value]

    if isinstance(value, BaseException):
        return {
            "type": type(value).__name__,
            "message": str(value),
        }

    return value


class JsonLogFormatter(logging.Formatter):
    """Serialize log records into a single JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "payload", {})
        return json.dumps(payload, ensure_ascii=True, default=str)


class ServiceLogger:
    """Structured logger with JSON stdout and rotating JSON log files."""

    def __init__(
        self,
        service_name: str,
        log_dir: Optional[str] = None,
        environment: Optional[str] = None,
        level: str = "INFO",
    ) -> None:
        self.service_name = service_name
        self.environment = environment or os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development"))
        self.log_dir = log_dir or _default_log_dir()
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_path = os.path.join(self.log_dir, f"{service_name}_service.log")
        self.logger = logging.getLogger(f"ragapp.{service_name}")
        self.logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        self.logger.propagate = False
        self._configure_handlers()

    def _configure_handlers(self) -> None:
        if self.logger.handlers:
            return

        formatter = JsonLogFormatter()

        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        stdout_handler.setLevel(self.logger.level)

        file_handler = RotatingFileHandler(
            self.log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(self.logger.level)

        self.logger.addHandler(stdout_handler)
        self.logger.addHandler(file_handler)

    def bind(self, **context: Optional[str]) -> "BoundServiceLogger":
        """Return a lightweight logger wrapper that merges fixed context values."""
        return BoundServiceLogger(self, context)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit("DEBUG", None, message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit("INFO", None, message, *args, **kwargs)

    def warning(self, *args: Any, **kwargs: Any) -> None:
        self.warn(*args, **kwargs)

    def warn(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit("WARNING", None, message, *args, **kwargs)

    def error(self, *args: Any, **kwargs: Any) -> None:
        if len(args) >= 3 and isinstance(args[0], str) and isinstance(args[1], str):
            location = args[0]
            message = args[1]
            error = args[2]
            extra = kwargs.pop("data", {}) or {}
            self._emit("ERROR", location, message, error=error, data=extra, **kwargs)
            return

        message = str(args[0]) if args else "Unexpected error"
        remaining = args[1:] if len(args) > 1 else ()
        self._emit("ERROR", None, message, *remaining, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        error = kwargs.pop("error", None) or kwargs.get("exc_info")
        self._emit("ERROR", None, message, *args, error=error, include_trace=True, **kwargs)

    def event(self, location: str, message: str, data: Optional[Mapping[str, Any]] = None) -> None:
        self._emit("INFO", location, message, data=data, event_type="event")

    def audit(self, location: str, message: str, data: Optional[Mapping[str, Any]] = None) -> None:
        self._emit("INFO", location, message, data=data, event_type="audit")

    def access(
        self,
        route: str,
        method: str,
        status_code: int,
        latency_ms: float,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        data: Dict[str, Any] = {
            "route": route,
            "method": method,
            "status_code": status_code,
            "latency_ms": latency_ms,
        }
        if request_id:
            data["request_id"] = request_id
        if trace_id:
            data["trace_id"] = trace_id
        if correlation_id:
            data["correlation_id"] = correlation_id
        self._emit("INFO", "http:access", "HTTP request completed", data=data, event_type="access")

    def log(
        self,
        location: str,
        message: str,
        data: Optional[Mapping[str, Any]] = None,
        hypothesis_id: str = "A",
        **kwargs: Any,
    ) -> None:
        self._emit(
            "INFO",
            location,
            message,
            data=data,
            hypothesis_id=hypothesis_id,
            event_type=kwargs.pop("event_type", "log"),
            **kwargs,
        )

    def _emit(
        self,
        level_name: str,
        location: Optional[str],
        message: str,
        *args: Any,
        data: Optional[Mapping[str, Any]] = None,
        hypothesis_id: Optional[str] = None,
        event_type: str = "log",
        error: Optional[Any] = None,
        include_trace: bool = False,
        exc_info: Any = None,
        **kwargs: Any,
    ) -> None:
        if args and error is None:
            if len(args) == 1 and isinstance(args[0], BaseException):
                error = args[0]
            elif not data:
                data = {"args": [redact_value(arg) for arg in args]}

        payload = self._build_payload(
            level_name=level_name,
            location=location,
            message=message,
            data=data,
            hypothesis_id=hypothesis_id,
            event_type=event_type,
            error=error,
            include_trace=include_trace,
            exc_info=exc_info,
            extra=kwargs,
        )
        self.logger.log(getattr(logging, level_name.upper(), logging.INFO), message, extra={"payload": payload})

    def _build_payload(
        self,
        *,
        level_name: str,
        location: Optional[str],
        message: str,
        data: Optional[Mapping[str, Any]],
        hypothesis_id: Optional[str],
        event_type: str,
        error: Optional[Any],
        include_trace: bool,
        exc_info: Any,
        extra: Mapping[str, Any],
    ) -> Dict[str, Any]:
        context = redact_value(get_context())
        merged_data: MutableMapping[str, Any] = {}
        if isinstance(context, Mapping):
            merged_data.update(context)
        if data:
            merged_data.update(redact_value(dict(data)))
        if extra:
            merged_data.update(redact_value(dict(extra)))

        payload: Dict[str, Any] = {
            "timestamp": int(time.time() * 1000),
            "level": level_name.lower(),
            "service": self.service_name,
            "environment": self.environment,
            "event_type": event_type,
            "message": message,
            "data": dict(merged_data),
        }
        if location:
            payload["location"] = location
        if hypothesis_id:
            payload["hypothesisId"] = hypothesis_id
        for key in ("request_id", "trace_id", "correlation_id", "route", "method", "topic", "action", "tenant_id", "user_id", "role", "admin_id", "session_id", "connection_id"):
            value = merged_data.get(key)
            if value is not None:
                payload[key] = value
        for key in ("status_code", "latency_ms"):
            if key in merged_data:
                payload[key] = merged_data[key]

        serialized_error = serialize_exception(error or exc_info, include_trace=include_trace)
        if serialized_error:
            payload["error"] = serialized_error
        return payload


class BoundServiceLogger:
    """Logger wrapper that injects fixed context into each call."""

    def __init__(self, base_logger: ServiceLogger, bound_data: Mapping[str, Any]) -> None:
        self._base_logger = base_logger
        self._bound_data = dict(bound_data)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base_logger, name)

    def log(self, location: str, message: str, data: Optional[Mapping[str, Any]] = None, hypothesis_id: str = "A", **kwargs: Any) -> None:
        merged = dict(self._bound_data)
        if data:
            merged.update(data)
        self._base_logger.log(location, message, merged, hypothesis_id=hypothesis_id, **kwargs)


def serialize_exception(error: Any, *, include_trace: bool = False) -> Optional[Dict[str, Any]]:
    """Serialize exception metadata for structured logs."""
    if error is None or error is False:
        return None

    exc = error if isinstance(error, BaseException) else None
    payload: Dict[str, Any] = {
        "error_type": type(error).__name__,
        "message": str(error),
    }
    if include_trace and exc is not None:
        payload["stack"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return cast(Dict[str, Any], redact_value(payload))


def setup_logging(service_name: str, log_level: str = "INFO", log_dir: Optional[str] = None) -> ServiceLogger:
    """Compatibility helper returning the canonical structured logger."""
    return ServiceLogger(service_name=service_name, log_dir=log_dir, level=log_level)
