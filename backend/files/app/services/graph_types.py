"""Shared data types for the file ingestion graph."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict

from app.core.config import Settings


@dataclass
class OutboundMessage:
    """A pipeline message that should be published after the transaction commits."""

    topic: str
    message: Dict[str, Any]


class FilesLangSmithTracer:
    """Lightweight LangSmith tracer wrapper with a no-op fallback."""

    def __init__(self, config: Settings):
        self.config = config
        self.enabled = bool(config.langsmith_tracing_enabled and config.langsmith_api_key)

    @contextmanager
    def span(self, name: str, metadata: Dict[str, Any]):
        _ = (name, metadata)
        yield
