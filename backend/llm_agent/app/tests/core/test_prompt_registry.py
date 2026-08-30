"""Tests for typed prompt registry selection."""
import unittest

from app.core.config import Settings
from app.llm.prompt_registry import PromptRegistry, _extract_json_payload_with_metadata


class PromptRegistryTests(unittest.TestCase):
    """Validate prompt registry routing and versioning."""

    def test_prompt_registry_returns_expected_entry(self):
        registry = PromptRegistry(Settings())

        entry = registry.resolve("answer_generation", None)

        self.assertEqual(entry.request_type, "answer_generation")
        self.assertEqual(entry.prompt_version, "answer_generation.v1")
        self.assertTrue(entry.streaming_allowed)

    def test_prompt_registry_rejects_unknown_version(self):
        registry = PromptRegistry(Settings())

        with self.assertRaises(ValueError):
            registry.resolve("answer_generation", "answer_generation.v999")

    def test_prompt_registry_supports_all_current_request_types(self):
        registry = PromptRegistry(Settings())

        for request_type in (
            "answer_generation",
            "answer_evaluation",
            "content_risk_scan",
            "query_rewrite",
            "memory_extraction",
            "chat_title",
            "chat_summary",
            "memory_curation",
        ):
            with self.subTest(request_type=request_type):
                entry = registry.resolve(request_type, None)
                self.assertEqual(entry.request_type, request_type)
                self.assertTrue(entry.prompt_version.startswith(f"{request_type}."))

    def test_prompt_registry_defaults_targeted_structured_requests_to_v2(self):
        registry = PromptRegistry(Settings())

        self.assertEqual(registry.resolve("answer_evaluation", None).prompt_version, "answer_evaluation.v2")
        self.assertEqual(registry.resolve("content_risk_scan", None).prompt_version, "content_risk_scan.v2")
        self.assertEqual(registry.resolve("memory_curation", None).prompt_version, "memory_curation.v2")

    def test_prompt_registry_keeps_v1_and_v2_resolvable_for_targeted_requests(self):
        registry = PromptRegistry(Settings())

        self.assertEqual(
            registry.resolve("answer_evaluation", "answer_evaluation.v1").prompt_version,
            "answer_evaluation.v1",
        )
        self.assertEqual(
            registry.resolve("answer_evaluation", "answer_evaluation.v2").prompt_version,
            "answer_evaluation.v2",
        )
        self.assertEqual(
            registry.resolve("content_risk_scan", "content_risk_scan.v1").prompt_version,
            "content_risk_scan.v1",
        )
        self.assertEqual(
            registry.resolve("content_risk_scan", "content_risk_scan.v2").prompt_version,
            "content_risk_scan.v2",
        )
        self.assertEqual(
            registry.resolve("memory_curation", "memory_curation.v1").prompt_version,
            "memory_curation.v1",
        )
        self.assertEqual(
            registry.resolve("memory_curation", "memory_curation.v2").prompt_version,
            "memory_curation.v2",
        )

    def test_structured_extractor_selects_last_valid_payload_when_multiple_objects_exist(self):
        extracted = _extract_json_payload_with_metadata(
            '{"risk_level":"medium","categories":["prompt_injection"],"flags":[],"summary":"first"} '
            '{"risk_level":"low","categories":["none"],"flags":[],"summary":"second"}'
        )

        self.assertEqual(extracted.metadata["payload_count"], 2)
        self.assertEqual(extracted.metadata["selected_payload_index"], 1)
        self.assertEqual(extracted.metadata["extraction_mode"], "multi_payload_last_valid")
        self.assertEqual(extracted.payload["summary"], "second")

    def test_structured_extractor_handles_braces_inside_quoted_strings(self):
        extracted = _extract_json_payload_with_metadata(
            '{"risk_level":"low","categories":["none"],'
            '"flags":[{"code":"x","span":"{literal}","rationale":"keep"}],"summary":"ok"}'
        )

        self.assertEqual(extracted.metadata["payload_count"], 1)
        self.assertEqual(extracted.payload["flags"][0]["span"], "{literal}")
