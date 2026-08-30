"""Structured-output transport, parsing, normalization and fail-closed errors."""
from __future__ import annotations

import unittest

from app.schemas.llm import AnswerReviewParsedOutput
from app.services.llm_service import LLMService
from app.tests._service_harness import (
    EVALUATION_INPUT,
    RISK_SCAN_INPUT,
    VALID_INPUTS,
    VALID_RESPONSES,
    FakeLLMClient,
    FakeLogger,
    request_message,
    settings,
)


def _service(responses, logger=None, **setting_overrides):
    return LLMService(
        FakeLLMClient(responses),
        logger or FakeLogger(),
        settings(**setting_overrides),
    )


class StructuredOutputTransportTests(unittest.TestCase):
    """Which actions get a JSON schema, and where that schema comes from."""

    def test_answer_evaluation_json_schema_comes_from_authoritative_model(self):
        client = FakeLLMClient(
            {"answer_evaluation": '{"verdict":"pass","issues":[],"revision_applied":false}'}
        )
        service = LLMService(
            client,
            FakeLogger(),
            settings(answer_evaluation_structured_output_transport="json_schema"),
        )

        service.execute(request_message("answer_evaluation", VALID_INPUTS["answer_evaluation"]))

        metadata = client.invocations[0].metadata
        self.assertEqual(metadata["structured_output_transport"], "json_schema")
        self.assertEqual(
            metadata["structured_output_schema"],
            AnswerReviewParsedOutput.model_json_schema(),
        )

    def test_json_schema_transport_is_scoped_to_answer_evaluation(self):
        client = FakeLLMClient({"content_risk_scan": VALID_RESPONSES["content_risk_scan"]})
        service = LLMService(
            client,
            FakeLogger(),
            settings(answer_evaluation_structured_output_transport="json_schema"),
        )

        service.execute(request_message("content_risk_scan", VALID_INPUTS["content_risk_scan"]))

        metadata = client.invocations[0].metadata
        self.assertEqual(metadata["structured_output_transport"], "legacy")
        self.assertIsNone(metadata["structured_output_schema"])


class AnswerEvaluationParsingTests(unittest.TestCase):
    def test_parse_success_uses_shared_answer_review_shape(self):
        service = _service(
            {
                "answer_evaluation": (
                    '{"verdict":"pass","groundedness_score":0.95,"completeness_score":0.8,'
                    '"safety_score":1.0,"issues":["minor omission"],"revision_applied":false}'
                )
            }
        )

        reply = service.execute(request_message("answer_evaluation", EVALUATION_INPUT))

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.verdict, "pass")
        self.assertEqual(reply.parsed_output.model_name, "test-model")
        self.assertEqual(reply.trace.trace_id, "trace-1")
        self.assertTrue(reply.parsed_output.review_id.startswith("review_"))
        self.assertIsInstance(reply.parsed_output.created_at, int)

    def test_fenced_json_is_accepted(self):
        service = _service(
            {
                "answer_evaluation": (
                    "```json\n"
                    '{"verdict":"pass","groundedness_score":0.95,"completeness_score":0.8,'
                    '"safety_score":1.0,"issues":[],"revision_applied":false}\n'
                    "```"
                )
            }
        )

        reply = service.execute(request_message("answer_evaluation", EVALUATION_INPUT))

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.issues, [])

    def test_scalar_issues_and_string_scores_are_normalized(self):
        service = _service(
            {
                "answer_evaluation": (
                    '{"verdict":"revise","groundedness_score":"0.75","completeness_score":"0.60",'
                    '"safety_score":"1.0","issues":"needs citations","revision_applied":"false"}'
                )
            }
        )

        reply = service.execute(request_message("answer_evaluation", EVALUATION_INPUT))

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.issues, ["needs citations"])
        self.assertEqual(reply.parsed_output.groundedness_score, 0.75)
        self.assertFalse(reply.parsed_output.revision_applied)

    def test_missing_optional_score_normalizes_without_a_failure_log(self):
        logger = FakeLogger()
        service = _service(
            {
                "answer_evaluation": (
                    '{"verdict":"pass","groundedness_score":0.95,"completeness_score":0.8,'
                    '"issues":[],"revision_applied":false}'
                )
            },
            logger,
        )

        reply = service.execute(request_message("answer_evaluation", EVALUATION_INPUT))

        self.assertEqual(reply.status, "success")
        self.assertIsNone(reply.parsed_output.safety_score)
        self.assertFalse(
            any(
                entry["message"] == "Typed structured output handling failed"
                for entry in logger.entries
            )
        )

    def test_invalid_output_is_an_explicit_error(self):
        service = _service({"answer_evaluation": "not valid json"})

        reply = service.execute(request_message("answer_evaluation", EVALUATION_INPUT))

        self.assertEqual(reply.status, "error")
        self.assertIsNone(reply.parsed_output)
        self.assertEqual(reply.raw_output, "not valid json")
        self.assertEqual(reply.errors[0].code, "structured_output_invalid")

    def test_last_valid_payload_wins_when_multiple_objects_exist(self):
        service = _service(
            {
                "answer_evaluation": (
                    '{"verdict":"revise","groundedness_score":0.2,"completeness_score":0.3,'
                    '"safety_score":1.0,"issues":["first"],"revision_applied":false} '
                    '{"verdict":"pass","groundedness_score":0.95,"completeness_score":0.8,'
                    '"safety_score":1.0,"issues":[],"revision_applied":false}'
                )
            }
        )

        reply = service.execute(request_message("answer_evaluation", EVALUATION_INPUT))

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.verdict, "pass")
        self.assertEqual(reply.parsed_output.issues, [])


class ContentRiskScanParsingTests(unittest.TestCase):
    """The risk scan must stay typed and must fail closed."""

    def test_returns_typed_parsed_output(self):
        service = _service(
            {
                "content_risk_scan": (
                    '{"risk_level":"low","categories":["none"],'
                    '"flags":[],"summary":"No material policy issues detected."}'
                )
            }
        )

        reply = service.execute(
            request_message("content_risk_scan", {**RISK_SCAN_INPUT, "policy_hints": ["violence"]})
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.risk_level, "low")
        self.assertEqual(reply.parsed_output.categories, ["none"])
        self.assertEqual(reply.parsed_output.summary, "No material policy issues detected.")

    def test_fenced_json_is_accepted(self):
        service = _service(
            {
                "content_risk_scan": (
                    "```json\n"
                    '{"risk_level":"low","categories":["none"],"flags":[],'
                    '"summary":"No material policy issues detected."}\n'
                    "```"
                )
            }
        )

        reply = service.execute(request_message("content_risk_scan", RISK_SCAN_INPUT))

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.flags, [])

    def test_scalar_categories_and_flag_variants_are_normalized(self):
        service = _service(
            {
                "content_risk_scan": (
                    '{"risk_level":"medium","categories":"self-harm",'
                    '"flags":["self-harm mention",{"code":"escalation","reason":"Escalation risk"}],'
                    '"summary":"Potential risk detected."}'
                )
            }
        )

        reply = service.execute(
            request_message(
                "content_risk_scan",
                {"content": "Potentially risky sentence.", "policy_hints": ["self-harm"]},
            )
        )

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.categories, ["self-harm"])
        self.assertEqual(reply.parsed_output.flags[0].code, "self-harm mention")
        self.assertEqual(reply.parsed_output.flags[0].rationale, "self-harm mention")
        self.assertEqual(reply.parsed_output.flags[1].code, "escalation")
        self.assertEqual(reply.parsed_output.flags[1].rationale, "Escalation risk")

    def test_fails_closed_when_json_cannot_be_extracted(self):
        service = _service({"content_risk_scan": "definitely not json"})

        reply = service.execute(request_message("content_risk_scan", RISK_SCAN_INPUT))

        self.assertEqual(reply.status, "error")
        self.assertEqual(reply.errors[0].code, "structured_output_invalid")
        self.assertIn("Structured output parse failed", reply.errors[0].message)

    def test_last_valid_payload_wins_and_recovery_is_reported(self):
        logger = FakeLogger()
        service = _service(
            {
                "content_risk_scan": (
                    '{"risk_level":"medium","categories":["prompt_injection"],'
                    '"flags":[],"summary":"first"} '
                    '{"risk_level":"low","categories":["none"],"flags":[],"summary":"second"}'
                )
            },
            logger,
        )

        reply = service.execute(request_message("content_risk_scan", RISK_SCAN_INPUT))

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.summary, "second")
        self.assertTrue(
            any(
                "Structured output payload count: 2" in step
                for step in reply.visible_reasoning_steps
            )
        )
        self.assertTrue(
            any(
                entry["message"] == "Structured output multi-payload recovery succeeded"
                for entry in logger.entries
            )
        )

    def test_trailing_truncated_fragment_does_not_discard_complete_payloads(self):
        service = _service(
            {
                "content_risk_scan": (
                    '{"risk_level":"medium","categories":["prompt_injection"],'
                    '"flags":[],"summary":"first"} '
                    '{"risk_level":"low","categories":["none"],"flags":[],"summary":"selected"} '
                    '{"risk_level":"high"'
                )
            }
        )

        reply = service.execute(request_message("content_risk_scan", RISK_SCAN_INPUT))

        self.assertEqual(reply.status, "success")
        self.assertEqual(reply.parsed_output.summary, "selected")


class MemoryExtractionParsingTests(unittest.TestCase):
    def test_returns_typed_memories(self):
        service = _service(
            {
                "memory_extraction": (
                    '{"memories":[{"type":"preference","content":"User prefers concise summaries.",'
                    '"confidence":0.91,"action":"create","source_role":"user"}]}'
                )
            }
        )

        reply = service.execute(
            request_message(
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
        self.assertEqual(reply.parsed_output.memories[0].action, "create")
        self.assertEqual(len(reply.output_schema_sha256), 64)


class StructuredOutputFailureContractTests(unittest.TestCase):
    """Every structured action fails the same way, and says why."""

    def test_truncated_structured_outputs_remain_explicit_errors(self):
        for action in (
            "answer_evaluation",
            "content_risk_scan",
            "query_rewrite",
            "memory_extraction",
            "chat_title",
            "chat_summary",
            "memory_curation",
        ):
            with self.subTest(action=action):
                service = _service({action: '{"truncated":'})
                reply = service.execute(request_message(action, VALID_INPUTS[action]))
                self.assertEqual(reply.status, "error")
                self.assertEqual(reply.errors[0].code, "structured_output_invalid")

    def test_parse_failure_logs_extraction_metadata_when_available(self):
        logger = FakeLogger()
        service = _service(
            {"content_risk_scan": '{"risk_level":"low"} trailing text without complete json'},
            logger,
        )

        reply = service.execute(request_message("content_risk_scan", RISK_SCAN_INPUT))

        self.assertEqual(reply.status, "error")
        failure_entry = next(
            entry
            for entry in logger.entries
            if entry["message"] == "Typed structured output handling failed"
        )
        self.assertEqual(failure_entry["data"]["parse_stage"], "validation")
        self.assertEqual(failure_entry["data"]["payload_count"], 1)
        self.assertEqual(failure_entry["data"]["selected_payload_index"], 0)
