"""The provider's finish reason and this service's own status are separate.

A structured-output failure used to erase what the provider had reported: the
metric label became `error`, and a response truncated at `max_tokens` became
indistinguishable from a response the model completed normally and the parser
then rejected. Those are different failures — one is a budget, the other is a
malformed output — so every test here asserts that one fact never overwrites
the other, and that the provider's usage survives with it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.llm.interfaces import LLMUsage
from app.services.llm_service import LLMService, provider_finish_reason
from app.tests.test_llm_service import (
    FakeLLMClient,
    FakeLogger,
    RecordingMetrics,
    _request_message,
    _settings,
)


# A complete evaluator response, and the same response cut off mid-object the
# way a `length` finish leaves one.
VALID_REVIEW = (
    '{"verdict":"pass","groundedness_score":0.92,"completeness_score":0.85,'
    '"safety_score":1.0,"issues":[],"claims":[],"unsupported_claim_count":0,'
    '"hallucination_verdict":"none","revision_applied":false}'
)
TRUNCATED_REVIEW = '{"verdict":"pass","groundedness_score":0.92,"claims":[{"claim":"X'
# Parses as JSON and then fails the strict output model. The evaluator's own
# parser coerces defensively by design, so the validation stage is exercised
# through `query_rewrite`, whose contract is strict.
UNVALIDATABLE_REWRITE = '{"rewritten_query": {"not": "a string"}}'


def _rewrite_request():
    return _request_message("query_rewrite", {"query": "best cpu for embeddings"})


def _evaluation_request():
    return _request_message(
        "answer_evaluation",
        {
            "question": "What is the answer?",
            "answer": "The answer is 42.",
            "reference_context": "The answer is 42.",
        },
    )


def _execute(
    raw_output,
    *,
    finish_reason,
    usage=None,
    metrics=None,
    request_type="answer_evaluation",
):
    service = LLMService(
        FakeLLMClient(
            {request_type: raw_output},
            usage=usage,
            finish_reason=finish_reason,
        ),
        FakeLogger(),
        _settings(),
    )
    request = (
        _evaluation_request()
        if request_type == "answer_evaluation"
        else _rewrite_request()
    )
    if metrics is None:
        return service.execute(request)
    with patch("app.services.llm_service.METRICS", metrics):
        return service.execute(request)


class ProviderFinishReasonTests(unittest.TestCase):
    def test_stop_is_preserved(self):
        reply = _execute(VALID_REVIEW, finish_reason="stop")

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.provider_finish_reason, "stop")
        self.assertEqual(reply.application_status, "success")
        self.assertIsNone(reply.parse_stage)

    def test_length_is_preserved(self):
        reply = _execute(VALID_REVIEW, finish_reason="length")

        self.assertEqual(reply.provider_finish_reason, "length")
        self.assertEqual(reply.application_status, "success")

    def test_missing_finish_reason_uses_the_bounded_fallback(self):
        reply = _execute(VALID_REVIEW, finish_reason=None)

        self.assertEqual(reply.provider_finish_reason, "completed")

    def test_parse_failure_does_not_overwrite_length(self):
        metrics = RecordingMetrics()
        reply = _execute(TRUNCATED_REVIEW, finish_reason="length", metrics=metrics)

        self.assertEqual(reply.status, "error")
        self.assertEqual(reply.application_status, "structured_output_invalid")
        self.assertEqual(reply.parse_stage, "parse")
        # The whole point: the provider still says why generation stopped.
        self.assertEqual(reply.provider_finish_reason, "length")
        self.assertEqual(
            [
                labels["finish_reason"]
                for labels in metrics.llm_provider_finish_reasons_total.label_calls
            ],
            ["length"],
        )

    def test_validation_failure_does_not_overwrite_stop(self):
        reply = _execute(
            UNVALIDATABLE_REWRITE, finish_reason="stop", request_type="query_rewrite"
        )

        self.assertEqual(reply.status, "error")
        self.assertEqual(reply.application_status, "validation_error")
        self.assertEqual(reply.parse_stage, "validation")
        self.assertEqual(reply.provider_finish_reason, "stop")

    def test_provider_failure_fabricates_no_finish_reason(self):
        metrics = RecordingMetrics()
        service = LLMService(
            FakeLLMClient(exception=ConnectionError("vllm unreachable")),
            FakeLogger(),
            _settings(),
        )

        with patch("app.services.llm_service.METRICS", metrics):
            reply = service.execute(_evaluation_request())

        self.assertEqual(reply.status, "error")
        self.assertEqual(reply.application_status, "provider_error")
        self.assertEqual(reply.provider_finish_reason, "unknown")
        self.assertEqual(
            [
                labels["finish_reason"]
                for labels in metrics.llm_provider_finish_reasons_total.label_calls
            ],
            ["unknown"],
        )

    def test_timeout_is_its_own_application_status(self):
        service = LLMService(
            FakeLLMClient(exception=TimeoutError("provider timed out")),
            FakeLogger(),
            _settings(),
        )

        reply = service.execute(_evaluation_request())

        self.assertEqual(reply.application_status, "provider_timeout")
        self.assertEqual(reply.provider_finish_reason, "unknown")


class ProviderUsageSurvivesFailureTests(unittest.TestCase):
    def test_output_tokens_survive_a_parse_failure(self):
        usage = LLMUsage(
            provider="vllm", input_tokens=800, output_tokens=512, total_tokens=1312
        )
        reply = _execute(TRUNCATED_REVIEW, finish_reason="length", usage=usage)

        self.assertEqual(reply.application_status, "structured_output_invalid")
        # 512 output tokens against a 512 ceiling is the evidence the whole
        # budget question turns on; discarding it with the parse failure is
        # what made the truncation hypothesis unprovable.
        self.assertEqual(reply.usage.output_tokens, 512)
        self.assertEqual(reply.max_tokens, 512)

    def test_input_and_total_usage_survive_a_validation_failure(self):
        usage = LLMUsage(
            provider="vllm", input_tokens=640, output_tokens=120, total_tokens=760
        )
        reply = _execute(
            UNVALIDATABLE_REWRITE,
            finish_reason="stop",
            usage=usage,
            request_type="query_rewrite",
        )

        self.assertEqual(reply.usage.input_tokens, 640)
        self.assertEqual(reply.usage.total_tokens, 760)

    def test_missing_usage_is_never_fabricated(self):
        usage = LLMUsage(provider="vllm")
        reply = _execute(TRUNCATED_REVIEW, finish_reason="length", usage=usage)

        self.assertIsNone(reply.usage.input_tokens)
        self.assertIsNone(reply.usage.output_tokens)
        self.assertIsNone(reply.usage.total_tokens)


class ProviderFinishReasonMetricTests(unittest.TestCase):
    def test_unbounded_provider_text_is_collapsed(self):
        metrics = RecordingMetrics()
        _execute(VALID_REVIEW, finish_reason="some-new-vllm-reason", metrics=metrics)

        self.assertEqual(
            metrics.llm_provider_finish_reasons_total.label_calls[0]["finish_reason"],
            "other",
        )
        self.assertEqual(provider_finish_reason(None), "unknown")
        self.assertEqual(provider_finish_reason("  LENGTH "), "length")

    def test_application_status_is_a_separate_metric_and_carries_no_message(self):
        metrics = RecordingMetrics()
        _execute(TRUNCATED_REVIEW, finish_reason="length", metrics=metrics)

        error_labels = metrics.llm_errors_total.label_calls[0]
        self.assertEqual(error_labels["error_type"], "structured_output_invalid")
        provider_labels = metrics.llm_provider_finish_reasons_total.label_calls[0]
        self.assertEqual(provider_labels["finish_reason"], "length")
        self.assertNotIn("error_type", provider_labels)
        # No label anywhere carries the exception text.
        for metric in (
            metrics.llm_errors_total,
            metrics.llm_provider_finish_reasons_total,
            metrics.llm_finish_reasons_total,
        ):
            for labels in metric.label_calls:
                for value in labels.values():
                    self.assertNotIn("Structured output", str(value))


if __name__ == "__main__":
    unittest.main()
