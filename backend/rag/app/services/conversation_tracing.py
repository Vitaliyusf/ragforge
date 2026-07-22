"""LangSmith tracing helpers with safe no-op fallbacks."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from app.core.config import RAGConfig

try:  # pragma: no cover - depends on optional dependency behavior
    import langsmith
    _HAS_LANGSMITH = True
except ImportError:  # pragma: no cover
    langsmith = None
    _HAS_LANGSMITH = False


class ConversationTracer:
    """Small wrapper around LangSmith tracing with graceful fallback."""

    def __init__(self, config: RAGConfig):
        self.config = config
        self.enabled = bool(config.enable_langsmith_tracing and _HAS_LANGSMITH)

    @contextmanager
    def run(self, name: str, metadata: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """Create a top-level trace scope if LangSmith is available."""
        if not self.enabled:
            yield metadata
            return

        trace_fn = getattr(langsmith, "trace", None)
        if callable(trace_fn):
            with trace_fn(name=name, metadata=metadata, project_name=self.config.langsmith_project):
                yield metadata
            return
        yield metadata

    @contextmanager
    def span(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> Iterator[None]:
        """Create a child span if supported."""
        if not self.enabled:
            yield
            return

        trace_fn = getattr(langsmith, "trace", None)
        if callable(trace_fn):
            with trace_fn(name=name, metadata=metadata or {}, project_name=self.config.langsmith_project):
                yield
            return
        yield
