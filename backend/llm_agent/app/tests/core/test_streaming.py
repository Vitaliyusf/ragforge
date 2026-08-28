"""Token streaming: which actions stream, and what a stream reports once."""
from __future__ import annotations

import unittest
from typing import List
from unittest.mock import patch

from app.llm.interfaces import LLMUsage
from app.schemas.llm import ModelExecutionStreamPayload
from app.services.llm_service import LLMService
from app.tests._service_harness import (
    GENERATION_INPUT,
    FakeLLMClient,
    FakeLogger,
    RecordingMetrics,
    request_message,
    settings,
)


class StreamingTests(unittest.TestCase):
    def test_answer_generation_publishes_inner_stream_payloads(self):
        service = LLMService(FakeLLMClient(), FakeLogger(), settings())
        stream_events: List[ModelExecutionStreamPayload] = []

        reply = service.execute(
            request_message("answer_generation", GENERATION_INPUT, stream_to="rag.stream"),
            stream_events.append,
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(
            [event.event_type for event in stream_events],
            ["llm.token", "llm.token", "llm.done"],
        )
        self.assertEqual(reply.parsed_output.answer, "Hello world")

    def test_non_generation_requests_are_reply_only(self):
        service = LLMService(
            FakeLLMClient(
                {"query_rewrite": '{"rewritten_query":"best cpu embeddings","search_intent":"shopping"}'}
            ),
            FakeLogger(),
            settings(),
        )
        stream_events = []

        reply = service.execute(
            request_message(
                "query_rewrite",
                {"query": "best cpu for embeddings"},
                stream_to="rag.stream",
            ),
            stream_events.append,
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.rewritten_query, "best cpu embeddings")
        self.assertEqual(stream_events, [])

    def test_streaming_records_usage_metrics_once(self):
        metrics = RecordingMetrics()
        service = LLMService(
            FakeLLMClient(
                usage=LLMUsage(provider="vllm", input_tokens=11, output_tokens=2, total_tokens=13)
            ),
            FakeLogger(),
            settings(),
        )

        with patch("app.services.llm_service.METRICS", metrics):
            reply = service.execute(
                request_message("answer_generation", GENERATION_INPUT, stream_to="rag.stream"),
                lambda _event: None,
            )

        self.assertEqual(reply.usage.input_tokens, 11)
        self.assertEqual(reply.usage.output_tokens, 2)
        self.assertEqual(reply.usage.total_tokens, 13)
        self.assertEqual(
            [labels["direction"] for labels in metrics.llm_tokens_total.label_calls],
            ["input", "output", "total"],
        )
        self.assertEqual(metrics.llm_tokens_total.increments, [11, 2, 13])
        self.assertTrue(
            all(
                labels["request_type"] == "answer_generation"
                for labels in metrics.llm_tokens_total.label_calls
            )
        )
        self.assertEqual(metrics.llm_output_tokens.observations, [2])
        self.assertEqual(len(metrics.llm_finish_reasons_total.increments), 1)
