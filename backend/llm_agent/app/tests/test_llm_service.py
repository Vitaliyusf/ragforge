"""Tests for typed LLM execution service behavior."""
from __future__ import annotations

import unittest
import os
from typing import List
from unittest.mock import patch

from pydantic import ValidationError

from app.core.config import Settings
from app.llm.interfaces import ILLMClient, LLMGenerationResult, LLMInvocation, LLMUsage
from app.schemas.llm import (
    AnswerReviewParsedOutput,
    ModelExecutionStreamPayload,
    validate_model_execution_request_message,
)
from app.services.llm_service import LLMService, _metric_finish_reason
from app.services.text_window import SAFETY_MARGIN_TOKENS, estimate_tokens
from shared.context import bound_context


class FakeLogger:
    """Simple in-memory logger for service tests."""

    def __init__(self):
        self.entries = []

    def log(self, location, message, data=None, hypothesis_id="A"):
        self.entries.append(
            {
                "location": location,
                "message": message,
                "data": data or {},
                "hypothesis_id": hypothesis_id,
            }
        )


class FakeLLMClient(ILLMClient):
    """Configurable fake client for reply and streaming tests."""

    def __init__(self, responses=None, exception=None, usage=None, finish_reason="completed"):
        self.responses = responses or {}
        self.exception = exception
        self.finish_reason = finish_reason
        self.usage = usage or LLMUsage(
            provider="fake",
            input_tokens=5,
            output_tokens=3,
            total_tokens=8,
        )
        self.invocations = []

    def generate(self, invocation: LLMInvocation) -> LLMGenerationResult:
        self.invocations.append(invocation)
        if self.exception is not None:
            raise self.exception

        request_type = invocation.metadata.get("request_type")
        raw_output = self.responses.get(request_type, "default response")

        if invocation.on_token is not None:
            chunks = ["Hello", " world"]
            for index, token in enumerate(chunks):
                invocation.on_token(token, index)
            raw_output = "".join(chunks)

        return LLMGenerationResult(
            raw_output=raw_output,
            usage=self.usage,
            finish_reason=self.finish_reason,
        )

    def list_models(self) -> list:
        return ["test-model"]

    def is_available(self) -> bool:
        return True


class DummySpan:
    """Minimal span for fake tracing."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def finish(self, outputs=None, error=None):
        return None


class DummyTrace:
    """Capture metadata added during a request."""

    def __init__(self, metadata):
        self.metadata = dict(metadata)

    def span(self, name, inputs=None, metadata=None):
        if metadata:
            self.metadata.update(metadata)
        return DummySpan()

    def add_metadata(self, metadata):
        self.metadata.update(metadata)

    def finish(self, outputs=None, error=None):
        return None

    def snapshot(self):
        return type(
            "Snapshot",
            (),
            {
                "trace_id": self.metadata.get("trace_id", ""),
                "langsmith_run_id": None,
                "langsmith_trace_url": None,
            },
        )()


class DummyTracer:
    """Capture root trace metadata from the service."""

    def __init__(self):
        self.last_trace = None

    def start_execution(self, name, trace_id, inputs, metadata):
        self.last_trace = DummyTrace(metadata)
        return self.last_trace


class RecordingMetric:
    def __init__(self):
        self.label_calls = []
        self.increments = []
        self.observations = []

    def labels(self, **labels):
        self.label_calls.append(labels)
        return self

    def inc(self, value=1):
        self.increments.append(value)

    def observe(self, value):
        self.observations.append(value)


class RecordingMetrics:
    def __init__(self):
        self.llm_requests_total = RecordingMetric()
        self.llm_request_duration = RecordingMetric()
        self.llm_provider_duration = RecordingMetric()
        self.llm_errors_total = RecordingMetric()
        self.llm_tokens_total = RecordingMetric()
        self.llm_output_tokens = RecordingMetric()
        self.llm_finish_reasons_total = RecordingMetric()
        self.llm_provider_finish_reasons_total = RecordingMetric()


def _settings(**overrides):
    defaults = {
        "default_model": "test-model",
        "rag_chat_model": "test-model",
        "llm_implementation": "vllm",
        "debug_max_field_length": 48,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _request_message(request_type, input_payload, **overrides):
    payload = {
        "message_id": "msg-1",
        "message_type": "command",
        "action": request_type,
        "source_service": "gateway",
        "target_service": "llm_agent",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "correlation_id": "corr-1",
        "reply_to": "gateway.replies",
        "timestamp": 1730000000000,
        "payload": {
            "request_type": request_type,
            "input": input_payload,
            "metadata": {"tenant_id": "tenant-1"},
            "debug": {"include_visible_reasoning_steps": True},
        },
    }
    payload.update(overrides)
    return validate_model_execution_request_message(payload)


def env_action_order():
    return (
        "answer_generation",
        "answer_evaluation",
        "content_risk_scan",
        "query_rewrite",
        "memory_extraction",
    )


class LLMServiceTests(unittest.TestCase):
    """Validate normalized replies, parsing, streaming, and safety behavior."""

    def test_action_token_budgets_resolve_independently_with_safe_fallback(self):
        settings = _settings(
            vllm_max_tokens=512,
            answer_generation_max_tokens=101,
            answer_evaluation_max_tokens=202,
            content_risk_scan_max_tokens=303,
            query_rewrite_max_tokens=404,
            memory_extraction_max_tokens=505,
        )

        expected = {
            "answer_generation": 101,
            "answer_evaluation": 202,
            "content_risk_scan": 303,
            "query_rewrite": 404,
            "memory_extraction": 505,
        }
        self.assertEqual(
            {action: settings.max_tokens_for_request_type(action) for action in expected},
            expected,
        )
        self.assertEqual(settings.max_tokens_for_request_type("legacy_action"), 512)

    def test_action_token_budget_defaults_match_measured_candidate(self):
        settings = _settings(vllm_max_tokens=777)

        self.assertEqual(
            {
                action: settings.max_tokens_for_request_type(action)
                for action in Settings._ACTION_MAX_TOKEN_FIELDS
            },
            {
                "answer_generation": 128,
                "answer_evaluation": 512,
                "content_risk_scan": 128,
                "query_rewrite": 128,
                "memory_extraction": 512,
            },
        )
        self.assertEqual(settings.max_tokens_for_request_type("unknown"), 777)

    def test_action_budget_environment_overrides_are_independent(self):
        env = {
            "ANSWER_GENERATION_MAX_TOKENS": "201",
            "ANSWER_EVALUATION_MAX_TOKENS": "202",
            "CONTENT_RISK_SCAN_MAX_TOKENS": "203",
            "QUERY_REWRITE_MAX_TOKENS": "204",
            "MEMORY_EXTRACTION_MAX_TOKENS": "205",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = Settings()

        self.assertEqual(
            [settings.max_tokens_for_request_type(action) for action in env_action_order()],
            [201, 202, 203, 204, 205],
        )

    def test_summary_budget_remains_independent(self):
        settings = _settings(summary_max_tokens=2048, answer_generation_max_tokens=128)

        self.assertEqual(settings.summary_max_tokens, 2048)
        self.assertEqual(settings.max_tokens_for_request_type("answer_generation"), 128)

    def test_invalid_token_budgets_are_rejected(self):
        for field_name in ("vllm_max_tokens", *Settings._ACTION_MAX_TOKEN_FIELDS.values()):
            for invalid_value in (0, -1):
                with self.subTest(field_name=field_name, invalid_value=invalid_value):
                    with self.assertRaises(ValidationError):
                        _settings(**{field_name: invalid_value})

    def test_token_budget_cannot_exceed_context_window(self):
        with self.assertRaises(ValidationError):
            _settings(
                vllm_max_model_len=1024,
                summary_max_tokens=512,
                answer_generation_max_tokens=1025,
            )

    def test_request_specific_budget_reaches_typed_invocation(self):
        client = FakeLLMClient(
            {
                "content_risk_scan": (
                    '{"risk_level":"low","categories":[],"flags":[],"summary":"safe"}'
                )
            }
        )
        service = LLMService(
            client,
            FakeLogger(),
            _settings(content_risk_scan_max_tokens=89),
        )

        reply = service.execute(
            _request_message(
                "content_risk_scan",
                {"content": "A harmless sentence.", "policy_hints": []},
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(client.invocations[0].max_tokens, 89)
        self.assertEqual(client.invocations[0].metadata["structured_output_hint"], "json_object")

    def test_answer_evaluation_json_schema_comes_from_authoritative_model(self):
        client = FakeLLMClient(
            {
                "answer_evaluation": (
                    '{"verdict":"pass","issues":[],"revision_applied":false}'
                )
            }
        )
        service = LLMService(
            client,
            FakeLogger(),
            _settings(answer_evaluation_structured_output_transport="json_schema"),
        )

        service.execute(
            _request_message(
                "answer_evaluation",
                {"question": "Q?", "answer": "A.", "reference_context": "C."},
            )
        )

        metadata = client.invocations[0].metadata
        self.assertEqual(metadata["structured_output_transport"], "json_schema")
        self.assertEqual(
            metadata["structured_output_schema"],
            AnswerReviewParsedOutput.model_json_schema(),
        )

    def test_json_schema_transport_is_scoped_to_answer_evaluation(self):
        client = FakeLLMClient(
            {"content_risk_scan": '{"risk_level":"low","categories":[],"flags":[],"summary":"safe"}'}
        )
        service = LLMService(
            client,
            FakeLogger(),
            _settings(answer_evaluation_structured_output_transport="json_schema"),
        )

        service.execute(
            _request_message(
                "content_risk_scan",
                {"content": "A harmless sentence.", "policy_hints": []},
            )
        )

        metadata = client.invocations[0].metadata
        self.assertEqual(metadata["structured_output_transport"], "legacy")
        self.assertIsNone(metadata["structured_output_schema"])

    def test_all_candidate_budgets_reach_typed_invocations(self):
        responses = {
            "answer_generation": "A supported answer.",
            "answer_evaluation": (
                '{"verdict":"pass","groundedness_score":1,"completeness_score":1,'
                '"safety_score":1,"issues":[],"claims":[],"unsupported_claim_count":0,'
                '"hallucination_verdict":"none","revision_applied":false}'
            ),
            "content_risk_scan": (
                '{"risk_level":"low","categories":[],"flags":[],"summary":"safe"}'
            ),
            "query_rewrite": '{"rewritten_query":"widgets","search_intent":"lookup"}',
            "memory_extraction": '{"memories":[]}',
        }
        inputs = {
            "answer_generation": {"question": "Q?", "retrieved_context": "Context"},
            "answer_evaluation": {
                "question": "Q?",
                "answer": "A.",
                "reference_context": "Context",
            },
            "content_risk_scan": {"content": "safe", "policy_hints": []},
            "query_rewrite": {"query": "widgets"},
            "memory_extraction": {"conversation_history": []},
        }
        client = FakeLLMClient(responses)
        service = LLMService(client, FakeLogger(), _settings())

        for action in env_action_order():
            with self.subTest(action=action):
                self.assertEqual(service.execute(_request_message(action, inputs[action])).status, "success")

        self.assertEqual(
            {invocation.metadata["request_type"]: invocation.max_tokens for invocation in client.invocations},
            {
                "answer_generation": 128,
                "answer_evaluation": 512,
                "content_risk_scan": 128,
                "query_rewrite": 128,
                "memory_extraction": 512,
            },
        )

    def test_typed_prompt_reserves_its_effective_output_budget(self):
        client = FakeLLMClient({"answer_generation": "A concise answer."})
        settings = _settings(
            vllm_max_model_len=1024,
            summary_max_tokens=512,
            answer_generation_max_tokens=128,
        )
        service = LLMService(client, FakeLogger(), settings)

        reply = service.execute(
            _request_message(
                "answer_generation",
                {"question": "What?", "retrieved_context": "context " * 5000},
            )
        )

        invocation = client.invocations[0]
        self.assertEqual(reply.status, "success")
        self.assertLessEqual(
            estimate_tokens(invocation.system_prompt)
            + estimate_tokens(invocation.raw_prompt)
            + invocation.max_tokens
            + SAFETY_MARGIN_TOKENS,
            settings.vllm_max_model_len,
        )

    def test_truncated_structured_outputs_remain_explicit_errors(self):
        inputs = {
            "answer_evaluation": {
                "question": "Q?",
                "answer": "A.",
                "reference_context": "Context",
            },
            "content_risk_scan": {"content": "safe", "policy_hints": []},
            "query_rewrite": {"query": "widgets"},
            "memory_extraction": {"conversation_history": []},
        }
        for action, input_payload in inputs.items():
            with self.subTest(action=action):
                service = LLMService(
                    FakeLLMClient({action: '{"truncated":'}),
                    FakeLogger(),
                    _settings(),
                )
                reply = service.execute(_request_message(action, input_payload))
                self.assertEqual(reply.status, "error")
                self.assertEqual(reply.errors[0].code, "structured_output_invalid")

    def test_structured_parse_success_for_evaluation_uses_shared_answer_review_shape(self):
        service = LLMService(
            FakeLLMClient(
                {
                    "answer_evaluation": (
                        '{"verdict":"pass","groundedness_score":0.95,"completeness_score":0.8,'
                        '"safety_score":1.0,"issues":["minor omission"],"revision_applied":false}'
                    )
                }
            ),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "answer_evaluation",
                {
                    "question": "What is the answer?",
                    "answer": "The answer is 42.",
                    "reference_context": "Trusted source",
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.verdict, "pass")
        self.assertEqual(reply.parsed_output.model_name, "test-model")
        self.assertEqual(reply.trace.trace_id, "trace-1")
        self.assertTrue(reply.parsed_output.review_id.startswith("review_"))
        self.assertIsInstance(reply.parsed_output.created_at, int)

    def test_answer_evaluation_accepts_fenced_json(self):
        service = LLMService(
            FakeLLMClient(
                {
                    "answer_evaluation": (
                        "```json\n"
                        '{"verdict":"pass","groundedness_score":0.95,"completeness_score":0.8,'
                        '"safety_score":1.0,"issues":[],"revision_applied":false}\n'
                        "```"
                    )
                }
            ),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "answer_evaluation",
                {
                    "question": "What is the answer?",
                    "answer": "The answer is 42.",
                    "reference_context": "Trusted source",
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.issues, [])

    def test_answer_evaluation_normalizes_scalar_issues_and_string_scores(self):
        service = LLMService(
            FakeLLMClient(
                {
                    "answer_evaluation": (
                        '{"verdict":"revise","groundedness_score":"0.75","completeness_score":"0.60",'
                        '"safety_score":"1.0","issues":"needs citations","revision_applied":"false"}'
                    )
                }
            ),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "answer_evaluation",
                {
                    "question": "What is the answer?",
                    "answer": "The answer is 42.",
                    "reference_context": "Trusted source",
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.issues, ["needs citations"])
        self.assertEqual(reply.parsed_output.groundedness_score, 0.75)
        self.assertFalse(reply.parsed_output.revision_applied)

    def test_answer_evaluation_invalid_output_is_an_explicit_error(self):
        service = LLMService(
            FakeLLMClient({"answer_evaluation": "not valid json"}),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "answer_evaluation",
                {
                    "question": "What is the answer?",
                    "answer": "The answer is 42.",
                    "reference_context": "Trusted source",
                },
            )
        )

        self.assertEqual(reply.status, "error")
        self.assertIsNone(reply.parsed_output)
        self.assertEqual(reply.raw_output, "not valid json")
        self.assertEqual(reply.errors[0].code, "structured_output_invalid")

    def test_streaming_answer_generation_publishes_inner_stream_payloads(self):
        service = LLMService(FakeLLMClient(), FakeLogger(), _settings())
        stream_events: List[ModelExecutionStreamPayload] = []

        reply = service.execute(
            _request_message(
                "answer_generation",
                {
                    "question": "What is the answer?",
                    "retrieved_context": "Trusted source",
                },
                stream_to="rag.stream",
            ),
            stream_events.append,
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(
            [event.event_type for event in stream_events],
            ["llm.token", "llm.token", "llm.done"],
        )
        self.assertEqual(reply.parsed_output.answer, "Hello world")

    def test_streaming_answer_generation_records_usage_metrics_once(self):
        metrics = RecordingMetrics()
        service = LLMService(
            FakeLLMClient(
                usage=LLMUsage(
                    provider="vllm",
                    input_tokens=11,
                    output_tokens=2,
                    total_tokens=13,
                )
            ),
            FakeLogger(),
            _settings(),
        )

        with patch("app.services.llm_service.METRICS", metrics):
            reply = service.execute(
                _request_message(
                    "answer_generation",
                    {
                        "question": "What is the answer?",
                        "retrieved_context": "Trusted source",
                    },
                    stream_to="rag.stream",
                ),
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

    def test_non_generation_requests_are_reply_only(self):
        service = LLMService(
            FakeLLMClient({'query_rewrite': '{"rewritten_query":"best cpu embeddings","search_intent":"shopping"}'}),
            FakeLogger(),
            _settings(),
        )
        stream_events = []

        reply = service.execute(
            _request_message(
                "query_rewrite",
                {"query": "best cpu for embeddings"},
                stream_to="rag.stream",
            ),
            stream_events.append,
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.rewritten_query, "best cpu embeddings")
        self.assertEqual(stream_events, [])

    def test_content_risk_scan_returns_typed_parsed_output(self):
        service = LLMService(
            FakeLLMClient(
                {
                    "content_risk_scan": (
                        '{"risk_level":"low","categories":["none"],'
                        '"flags":[],"summary":"No material policy issues detected."}'
                    )
                }
            ),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "content_risk_scan",
                {
                    "content": "A short harmless sentence.",
                    "policy_hints": ["violence"],
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.risk_level, "low")
        self.assertEqual(reply.parsed_output.categories, ["none"])
        self.assertEqual(reply.parsed_output.summary, "No material policy issues detected.")

    def test_content_risk_scan_accepts_fenced_json(self):
        service = LLMService(
            FakeLLMClient(
                {
                    "content_risk_scan": (
                        "```json\n"
                        '{"risk_level":"low","categories":["none"],"flags":[],"summary":"No material policy issues detected."}\n'
                        "```"
                    )
                }
            ),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "content_risk_scan",
                {
                    "content": "A short harmless sentence.",
                    "policy_hints": ["violence"],
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.flags, [])

    def test_content_risk_scan_normalizes_scalar_categories_and_flag_variants(self):
        service = LLMService(
            FakeLLMClient(
                {
                    "content_risk_scan": (
                        '{"risk_level":"medium","categories":"self-harm",'
                        '"flags":["self-harm mention",{"code":"escalation","reason":"Escalation risk"}],'
                        '"summary":"Potential risk detected."}'
                    )
                }
            ),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "content_risk_scan",
                {
                    "content": "Potentially risky sentence.",
                    "policy_hints": ["self-harm"],
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.categories, ["self-harm"])
        self.assertEqual(reply.parsed_output.flags[0].code, "self-harm mention")
        self.assertEqual(reply.parsed_output.flags[0].rationale, "self-harm mention")
        self.assertEqual(reply.parsed_output.flags[1].code, "escalation")
        self.assertEqual(reply.parsed_output.flags[1].rationale, "Escalation risk")

    def test_content_risk_scan_still_fails_closed_when_json_cannot_be_extracted(self):
        service = LLMService(
            FakeLLMClient({"content_risk_scan": "definitely not json"}),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "content_risk_scan",
                {
                    "content": "A short harmless sentence.",
                    "policy_hints": ["violence"],
                },
            )
        )

        self.assertEqual(reply.status, "error")
        self.assertEqual(reply.errors[0].code, "structured_output_invalid")
        self.assertIn("Structured output parse failed", reply.errors[0].message)

    def test_content_risk_scan_selects_last_valid_payload_when_multiple_objects_exist(self):
        logger = FakeLogger()
        service = LLMService(
            FakeLLMClient(
                {
                    "content_risk_scan": (
                        '{"risk_level":"medium","categories":["prompt_injection"],"flags":[],"summary":"first"} '
                        '{"risk_level":"low","categories":["none"],"flags":[],"summary":"second"}'
                    )
                }
            ),
            logger,
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "content_risk_scan",
                {
                    "content": "A short harmless sentence.",
                    "policy_hints": ["violence"],
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.summary, "second")
        self.assertTrue(any("Structured output payload count: 2" in step for step in reply.visible_reasoning_steps))
        self.assertTrue(any(entry["message"] == "Structured output multi-payload recovery succeeded" for entry in logger.entries))

    def test_answer_evaluation_selects_last_valid_payload_when_multiple_objects_exist(self):
        service = LLMService(
            FakeLLMClient(
                {
                    "answer_evaluation": (
                        '{"verdict":"revise","groundedness_score":0.2,"completeness_score":0.3,'
                        '"safety_score":1.0,"issues":["first"],"revision_applied":false} '
                        '{"verdict":"pass","groundedness_score":0.95,"completeness_score":0.8,'
                        '"safety_score":1.0,"issues":[],"revision_applied":false}'
                    )
                }
            ),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "answer_evaluation",
                {
                    "question": "What is the answer?",
                    "answer": "The answer is 42.",
                    "reference_context": "Trusted source",
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.verdict, "pass")
        self.assertEqual(reply.parsed_output.issues, [])

    def test_content_risk_scan_recovers_when_last_fragment_is_truncated_after_complete_payloads(self):
        service = LLMService(
            FakeLLMClient(
                {
                    "content_risk_scan": (
                        '{"risk_level":"medium","categories":["prompt_injection"],"flags":[],"summary":"first"} '
                        '{"risk_level":"low","categories":["none"],"flags":[],"summary":"selected"} '
                        '{"risk_level":"high"'
                    )
                }
            ),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "content_risk_scan",
                {
                    "content": "A short harmless sentence.",
                    "policy_hints": ["violence"],
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.summary, "selected")

    def test_answer_evaluation_normalizes_missing_optional_score(self):
        logger = FakeLogger()
        service = LLMService(
            FakeLLMClient(
                {
                    "answer_evaluation": (
                        '{"verdict":"pass","groundedness_score":0.95,"completeness_score":0.8,'
                        '"issues":[],"revision_applied":false}'
                    )
                }
            ),
            logger,
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "answer_evaluation",
                {
                    "question": "What is the answer?",
                    "answer": "The answer is 42.",
                    "reference_context": "Trusted source",
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertIsNone(reply.parsed_output.safety_score)
        self.assertFalse(
            any(entry["message"] == "Typed structured output handling failed" for entry in logger.entries)
        )

    def test_structured_parse_failure_logs_extraction_metadata_when_available(self):
        logger = FakeLogger()
        service = LLMService(
            FakeLLMClient({"content_risk_scan": '{"risk_level":"low"} trailing text without complete json'}),
            logger,
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "content_risk_scan",
                {
                    "content": "A short harmless sentence.",
                    "policy_hints": ["violence"],
                },
            )
        )

        self.assertEqual(reply.status, "error")
        failure_entry = next(
            entry for entry in logger.entries if entry["message"] == "Typed structured output handling failed"
        )
        self.assertEqual(failure_entry["data"]["parse_stage"], "validation")
        self.assertEqual(failure_entry["data"]["payload_count"], 1)
        self.assertEqual(failure_entry["data"]["selected_payload_index"], 0)

    def test_memory_extraction_returns_typed_memories(self):
        service = LLMService(
            FakeLLMClient(
                {
                    "memory_extraction": (
                        '{"memories":[{"type":"preference","content":"User prefers concise summaries.",'
                        '"confidence":0.91,"action":"store"}]}'
                    )
                }
            ),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "memory_extraction",
                {
                    "conversation_history": [
                        {"role": "user", "content": "Please keep responses concise."}
                    ]
                },
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(len(reply.parsed_output.memories), 1)
        self.assertEqual(reply.parsed_output.memories[0].type, "preference")
        self.assertEqual(reply.parsed_output.memories[0].action, "store")

    def test_normalized_error_payload_on_provider_failure(self):
        service = LLMService(
            FakeLLMClient(exception=RuntimeError("provider exploded")),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(
            _request_message(
                "query_rewrite",
                {"query": "best cpu for embeddings"},
            )
        )

        self.assertEqual(reply.status, "error")
        self.assertEqual(reply.errors[0].code, "provider_error")
        self.assertEqual(reply.application_status, "provider_error")
        # No provider response arrived, so no finish reason is invented.
        self.assertEqual(reply.provider_finish_reason, "unknown")
        self.assertEqual(reply.usage.provider, "vllm")
        self.assertEqual(reply.prompt_version, "query_rewrite.v1")

    def test_redaction_and_truncation_are_applied_to_debug_fields(self):
        service = LLMService(
            FakeLLMClient(
                {
                    "answer_generation": "Authorization: Bearer secret-token " + ("x" * 100),
                }
            ),
            FakeLogger(),
            _settings(debug_max_field_length=32),
        )

        reply = service.execute(
            _request_message(
                "answer_generation",
                {
                    "question": "What is the answer?",
                    "retrieved_context": "Authorization: Bearer secret-token",
                },
            )
        )

        self.assertIn("[REDACTED]", reply.raw_output)
        self.assertIn("[TRUNCATED", reply.raw_output)

    def test_shared_trace_metadata_is_attached_when_present(self):
        service = LLMService(FakeLLMClient(), FakeLogger(), _settings())
        service.tracer = DummyTracer()

        request_message = _request_message(
            "answer_generation",
            {
                "question": "What is the answer?",
                "retrieved_context": "Trusted source",
            },
        )
        request_message.payload.metadata.update(
            {
                "conversation_id": "conv-1",
                "turn_id": "turn-1",
                "file_id": "file-1",
                "document_id": "doc-1",
                "graph_run_id": "graph-1",
                "mode": "chat",
            }
        )

        service.execute(request_message)

        self.assertEqual(service.tracer.last_trace.metadata["conversation_id"], "conv-1")
        self.assertEqual(service.tracer.last_trace.metadata["turn_id"], "turn-1")
        self.assertEqual(service.tracer.last_trace.metadata["file_id"], "file-1")
        self.assertEqual(service.tracer.last_trace.metadata["document_id"], "doc-1")
        self.assertEqual(service.tracer.last_trace.metadata["graph_run_id"], "graph-1")
        self.assertEqual(service.tracer.last_trace.metadata["mode"], "chat")

    def test_metrics_are_bounded_and_grouped_by_request_type_and_traffic_class(self):
        metrics = RecordingMetrics()
        success = LLMService(FakeLLMClient(), FakeLogger(), _settings())
        failure = LLMService(
            FakeLLMClient(exception=RuntimeError("provider exploded")),
            FakeLogger(),
            _settings(),
        )

        with patch("app.services.llm_service.METRICS", metrics):
            success.execute(
                _request_message(
                    "answer_generation",
                    {"question": "Q?", "retrieved_context": "Context"},
                )
            )
            with bound_context(traffic_class="eval"):
                failure.execute(
                    _request_message("query_rewrite", {"query": "rewrite me"})
                )

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
            all(
                "request_type" in labels
                for labels in metrics.llm_request_duration.label_calls
            )
        )
        self.assertEqual(
            metrics.llm_errors_total.label_calls[0]["traffic_class"], "eval"
        )
        self.assertEqual(
            metrics.llm_errors_total.label_calls[0]["request_type"], "query_rewrite"
        )
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
        self.assertTrue(
            all(
                labels["request_type"] == "answer_generation"
                for labels in metrics.llm_tokens_total.label_calls
            )
        )
        self.assertEqual(
            [
                labels["finish_reason"]
                for labels in metrics.llm_finish_reasons_total.label_calls
            ],
            ["completed", "error"],
        )
        self.assertEqual(
            _metric_finish_reason("request-specific-value", errored=False), "other"
        )

    def test_output_token_histogram_observes_reported_usage_and_skips_missing_usage(self):
        metrics = RecordingMetrics()
        reported = LLMService(
            FakeLLMClient(
                usage=LLMUsage(
                    provider="fake",
                    input_tokens=50,
                    output_tokens=42,
                    total_tokens=92,
                )
            ),
            FakeLogger(),
            _settings(),
        )
        missing = LLMService(
            FakeLLMClient(usage=LLMUsage(provider="fake")),
            FakeLogger(),
            _settings(),
        )

        with patch("app.services.llm_service.METRICS", metrics):
            reported.execute(
                _request_message(
                    "answer_generation",
                    {"question": "Q?", "retrieved_context": "Context"},
                )
            )
            missing.execute(
                _request_message(
                    "answer_generation",
                    {"question": "Q?", "retrieved_context": "Context"},
                    stream_to="rag.stream",
                ),
                lambda _event: None,
            )

        self.assertEqual(metrics.llm_output_tokens.observations, [42])
