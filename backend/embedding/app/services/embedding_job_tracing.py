"""LangSmith tracing helpers for typed embedding-job processing."""
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional


try:
    from langsmith.run_helpers import trace as _langsmith_trace
except Exception:  # pragma: no cover - optional dependency
    _langsmith_trace = None


class EmbeddingLangSmithTracer:
    """Minimal LangSmith adapter for the typed embedding-job worker.

    When tracing is disabled or LangSmith is unavailable, the adapter yields
    no-op spans so the worker can keep a single tracing call pattern.
    """

    def __init__(
        self,
        enabled: bool = False,
        api_key: Optional[str] = None,
        project: Optional[str] = None,
        trace_factory=None,
    ) -> None:
        self.enabled = enabled
        self.api_key = api_key
        self.project = project
        self._trace_factory = trace_factory

        if self.enabled:
            os.environ["LANGSMITH_TRACING"] = "true"
            if self.api_key:
                os.environ.setdefault("LANGSMITH_API_KEY", self.api_key)
            if self.project:
                os.environ.setdefault("LANGSMITH_PROJECT", self.project)

    def _get_trace_factory(self):
        if self._trace_factory is not None:
            return self._trace_factory
        return _langsmith_trace

    @contextmanager
    def span(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> Iterator[None]:
        """Yield a LangSmith span when available, otherwise a no-op context."""
        trace_factory = self._get_trace_factory()
        if not self.enabled or trace_factory is None:
            yield
            return

        metadata = metadata or {}

        try:
            context = trace_factory(
                name=name,
                run_type="chain",
                project_name=self.project,
                metadata=metadata,
            )
        except TypeError:
            try:
                context = trace_factory(name=name, metadata=metadata)
            except TypeError:
                context = trace_factory(name)

        with context:
            yield
