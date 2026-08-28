"""Tests for LangSmith tracing wrapper behavior."""
import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.core.tracing import ExecutionTracer
import app.core.tracing as tracing_module


class FakeRunTree:
    """Minimal fake RunTree for tracing tests."""

    next_id = 1

    def __init__(self, name, run_type, inputs):
        self.name = name
        self.run_type = run_type
        self.inputs = inputs
        self.metadata = {}
        self.children = []
        self.outputs = {}
        self.id = FakeRunTree.next_id
        FakeRunTree.next_id += 1

    def add_metadata(self, metadata):
        self.metadata.update(metadata)

    def post(self):
        return None

    def create_child(self, name, run_type, inputs):
        child = FakeRunTree(name=name, run_type=run_type, inputs=inputs)
        self.children.append(child)
        return child

    def end(self, outputs=None):
        self.outputs = outputs or {}

    def patch(self):
        return None

    def get_url(self):
        return f"https://langsmith.test/runs/{self.id}"


class TracingTests(unittest.TestCase):
    """Validate disabled and enabled tracing paths."""

    def test_langsmith_noop_when_disabled(self):
        tracer = ExecutionTracer(Settings(langsmith_enabled=False))

        trace = tracer.start_execution(
            name="answer_generation.execute",
            trace_id="trace-123",
            inputs={"request_id": "req-123"},
            metadata={"service": "llm_agent"},
        )
        trace.finish(outputs={"status": "success"})

        snapshot = trace.snapshot()

        self.assertEqual(snapshot.trace_id, "trace-123")
        self.assertIsNone(snapshot.langsmith_run_id)

    def test_langsmith_enabled_uses_run_tree(self):
        with patch.object(tracing_module, "_LangSmithRunTree", FakeRunTree):
            tracer = ExecutionTracer(
                Settings(
                    langsmith_enabled=True,
                    langsmith_api_key="lsv2_test_value",
                    langsmith_project="llm_agent",
                )
            )

            trace = tracer.start_execution(
                name="answer_generation.execute",
                trace_id="trace-456",
                inputs={"request_id": "req-456"},
                metadata={"service": "llm_agent"},
            )
            with trace.span("prompt_render", inputs={"request_type": "answer_generation"}):
                pass
            trace.finish(outputs={"status": "success"})

            snapshot = trace.snapshot()

            self.assertEqual(snapshot.trace_id, "trace-456")
            self.assertIsNotNone(snapshot.langsmith_run_id)
            self.assertIsNotNone(snapshot.langsmith_trace_url)
