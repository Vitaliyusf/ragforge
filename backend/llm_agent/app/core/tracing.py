"""LangSmith tracing wrapper with a no-op fallback."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.core.config import Settings

try:
    from langsmith.run_trees import RunTree as _LangSmithRunTree
except ImportError:  # pragma: no cover - exercised via the no-op path
    _LangSmithRunTree = None


@dataclass
class TraceSnapshot:
    """Trace data returned in the normalized reply envelope."""

    trace_id: str
    langsmith_run_id: Optional[str] = None
    langsmith_trace_url: Optional[str] = None


class _NullSpan:
    """No-op context manager for tracing-disabled environments."""

    def __enter__(self) -> "_NullSpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.finish(error=exc)

    def finish(self, outputs: Optional[Dict[str, Any]] = None, error: Optional[Exception] = None) -> None:
        return None


class _RunTreeSpan:
    """Thin wrapper around a LangSmith child run."""

    def __init__(self, run_tree: Any):
        self._run_tree = run_tree
        self._finished = False
        self._run_tree.post()

    def __enter__(self) -> "_RunTreeSpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.finish(error=exc)

    def finish(self, outputs: Optional[Dict[str, Any]] = None, error: Optional[Exception] = None) -> None:
        if self._finished:
            return

        if error is not None:
            self._run_tree.add_metadata(
                {"error": str(error), "error_type": type(error).__name__}
            )

        self._run_tree.end(outputs=outputs or {})
        self._run_tree.patch()
        self._finished = True


class _NullExecutionTrace:
    """Trace facade used when LangSmith is disabled or unavailable."""

    def __init__(self, trace_id: str):
        self._snapshot = TraceSnapshot(trace_id=trace_id)

    def span(
        self,
        name: str,
        inputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> _NullSpan:
        return _NullSpan()

    def add_metadata(self, metadata: Dict[str, Any]) -> None:
        return None

    def finish(
        self,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ) -> None:
        return None

    def snapshot(self) -> TraceSnapshot:
        return self._snapshot


class _LangSmithExecutionTrace:
    """Trace facade backed by LangSmith RunTree spans."""

    def __init__(self, root_run: Any, trace_id: str):
        self._root_run = root_run
        self._trace_id = trace_id
        self._finished = False
        self._root_run.post()

    def span(
        self,
        name: str,
        inputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> _RunTreeSpan:
        child = self._root_run.create_child(
            name=name,
            run_type="chain",
            inputs=inputs or {},
        )
        if metadata:
            child.add_metadata(metadata)
        return _RunTreeSpan(child)

    def add_metadata(self, metadata: Dict[str, Any]) -> None:
        self._root_run.add_metadata(metadata)

    def finish(
        self,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ) -> None:
        if self._finished:
            return

        if error is not None:
            self._root_run.add_metadata(
                {"error": str(error), "error_type": type(error).__name__}
            )

        self._root_run.end(outputs=outputs or {})
        self._root_run.patch()
        self._finished = True

    def snapshot(self) -> TraceSnapshot:
        run_id = str(getattr(self._root_run, "id", "")) or None
        try:
            trace_url = self._root_run.get_url()
        except Exception:  # pragma: no cover - defensive for SDK differences
            trace_url = None
        return TraceSnapshot(
            trace_id=self._trace_id,
            langsmith_run_id=run_id,
            langsmith_trace_url=trace_url,
        )


class ExecutionTracer:
    """Factory for LangSmith-backed execution traces."""

    def __init__(self, config: Settings):
        self.config = config
        self._enabled = bool(config.langsmith_enabled and _LangSmithRunTree is not None)

        if config.langsmith_api_key:
            os.environ.setdefault("LANGSMITH_API_KEY", config.langsmith_api_key)
        if config.langsmith_project:
            os.environ.setdefault("LANGSMITH_PROJECT", config.langsmith_project)
        if config.langsmith_endpoint:
            os.environ.setdefault("LANGSMITH_ENDPOINT", config.langsmith_endpoint)
        os.environ.setdefault("LANGSMITH_TRACING", "true" if self._enabled else "false")

    def start_execution(
        self,
        name: str,
        trace_id: str,
        inputs: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> _NullExecutionTrace | _LangSmithExecutionTrace:
        """Start a root trace for one typed execution request."""
        if not self._enabled:
            return _NullExecutionTrace(trace_id=trace_id)

        try:
            run = _LangSmithRunTree(
                name=name,
                run_type="chain",
                inputs=inputs,
            )
            run.add_metadata(metadata)
            return _LangSmithExecutionTrace(run, trace_id=trace_id)
        except Exception:
            return _NullExecutionTrace(trace_id=trace_id)
