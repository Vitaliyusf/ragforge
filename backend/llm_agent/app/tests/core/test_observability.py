"""Error normalization, debug redaction, trace metadata and bounded metrics.

Provider finish-reason semantics are owned by the provider lane
(`app/tests/provider/test_provider_finish_reason.py`); this module only asserts
that the service reports its own request outcome and keeps metric labels bounded.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from shared.context import bound_context

from app.llm.interfaces import LLMUsage
from app.services.llm_service import LLMService, _metric_finish_reason
from app.tests._service_harness import (
    GENERATION_INPUT,
    VALID_INPUTS,
    DummyTracer,
    FakeLLMClient,
    FakeLogger,
    RecordingMetrics,
    request_message,
    settings,
)


class ProviderFailureReplyTests(unittest.TestCase):
    def test_normalized_error_payload_on_provider_failure(self):
        service = LLMService(
            FakeLLMClient(exception=RuntimeError("provider exploded")),
            FakeLogger(),
            settings(),
        )

        reply = service.execute(
            request_message("query_rewrite", {"query": "best cpu for embeddings"})
        )

        self.assertEqual(reply.status, "error")
        self.assertEqual(reply.errors[0].code, "provider_error")
        self.assertEqual(reply.application_status, "provider_error")
        # No provider response arrived, so no finish reason is invented.
        self.assertEqual(reply.provider_finish_reason, "unknown")
        self.assertEqual(reply.usage.provider, "vllm")
        self.assertEqual(reply.prompt_version, "query_rewrite.v1")


class DebugFieldSafetyTests(unittest.TestCase):
    def test_redaction_and_truncation_are_applied_to_debug_fields(self):
        service = LLMService(
            FakeLLMClient(
                {"answer_generation": "Authorization: Bearer secret-token " + ("x" * 100)}
            ),
            FakeLogger(),
            settings(debug_max_field_length=32),
        )

        reply = service.execute(
            request_message(
                "answer_generation",
                {
                    "question": "What is the answer?",
                    "retrieved_context": "Authorization: Bearer secret-token",
                },
            )
        )

        self.assertIn("[REDACTED]", reply.raw_output)
        self.assertIn("[TRUNCATED", reply.raw_output)


class TraceMetadataTests(unittest.TestCase):
    def test_shared_trace_metadata_is_attached_when_present(self):
        service = LLMService(FakeLLMClient(), FakeLogger(), settings())
        service.tracer = DummyTracer()

        message = request_message("answer_generation", GENERATION_INPUT)
        message.payload.metadata.update(
            {
                "conversation_id": "conv-1",
                "turn_id": "turn-1",
                "file_id": "file-1",
                "document_id": "doc-1",
                "graph_run_id": "graph-1",
                "mode": "chat",
            }
        )

        service.execute(message)

        attached = service.tracer.last_trace.metadata
        self.assertEqual(
            {key: attached[key] for key in ("conversation_id", "turn_id", "file_id")},
            {"conversation_id": "conv-1", "turn_id": "turn-1", "file_id": "file-1"},
        )
        self.assertEqual(attached["document_id"], "doc-1")
        self.assertEqual(attached["graph_run_id"], "graph-1")
        self.assertEqual(attached["mode"], "chat")


class MetricCardinalityTests(unittest.TestCase):
    """Labels stay bounded and always carry request type and traffic class."""

    def test_metrics_are_bounded_and_grouped_by_request_type_and_traffic_class(self):
        metrics = RecordingMetrics()
        success = LLMService(FakeLLMClient(), FakeLogger(), settings())
        failure = LLMService(
            FakeLLMClient(exception=RuntimeError("provider exploded")),
            FakeLogger(),
            settings(),
        )

        with patch("app.services.llm_service.METRICS", metrics):
            success.execute(
                request_message("answer_generation", VALID_INPUTS["answer_generation"])
            )
            with bound_context(traffic_class="eval"):
                failure.execute(request_message("query_rewrite", {"query": "rewrite me"}))

        request_labels = metrics.llm_requests_total.label_calls
        self.assertEqual(
            [labels["request_type"] for labels in request_labels],
            ["answer_generation", "query_rewrite"],
        )
        self.assertEqual(
            [labels["traffic_class"] for labels in request_labels],
            ["live", "eval"],
        )
        self.assertTrue(
            all("request_type" in labels for labels in metrics.llm_request_duration.label_calls)
        )
        self.assertEqual(metrics.llm_errors_total.label_calls[0]["traffic_class"], "eval")
        self.assertEqual(metrics.llm_errors_total.label_calls[0]["request_type"], "query_rewrite")
        self.assertEqual(
            [labels["direction"] for labels in metrics.llm_tokens_total.label_calls],
            ["input", "output", "total"],
        )
        self.assertEqual(metrics.llm_tokens_total.increments, [5, 3, 8])
        self.assertEqual(metrics.llm_output_tokens.observations, [3])
        self.assertEqual(
            set(metrics.llm_output_tokens.label_calls[0]),
            {"service", "request_type", "traffic_class"},
        )
        self.assertEqual(
            [labels["finish_reason"] for labels in metrics.llm_finish_reasons_total.label_calls],
            ["completed", "error"],
        )

    def test_service_finish_reason_label_collapses_unknown_values(self):
        self.assertEqual(_metric_finish_reason("request-specific-value", errored=False), "other")

    def test_output_token_histogram_observes_reported_usage_and_skips_missing_usage(self):
        metrics = RecordingMetrics()
        reported = LLMService(
            FakeLLMClient(
                usage=LLMUsage(provider="fake", input_tokens=50, output_tokens=42, total_tokens=92)
            ),
            FakeLogger(),
            settings(),
        )
        missing = LLMService(
            FakeLLMClient(usage=LLMUsage(provider="fake")),
            FakeLogger(),
            settings(),
        )

        with patch("app.services.llm_service.METRICS", metrics):
            reported.execute(
                request_message("answer_generation", VALID_INPUTS["answer_generation"])
            )
            missing.execute(
                request_message(
                    "answer_generation",
                    VALID_INPUTS["answer_generation"],
                    stream_to="rag.stream",
                ),
                lambda _event: None,
            )

        self.assertEqual(metrics.llm_output_tokens.observations, [42])
