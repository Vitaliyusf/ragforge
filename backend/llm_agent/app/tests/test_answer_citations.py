"""Tests for inline answer citations and the judge's claim decomposition."""
import unittest
from unittest.mock import patch

from app.llm.prompts import answer_generation
from app.llm.prompts.answer_evaluation import _normalize_payload, parse as parse_review
from app.schemas.llm import AnswerGenerationParsedOutput, AnswerGenerationRequest


def _request(passages):
    return AnswerGenerationRequest(
        request_type="answer_generation",
        metadata={},
        input={"question": "What is alpha?", "retrieved_context": passages},
    )


PASSAGES = [
    {"source_id": "chunk-a", "text": "Alpha is the first letter."},
    {"source_id": "chunk-b", "text": "Beta is the second letter."},
]


class AnswerCitationParseTests(unittest.TestCase):
    """Marker extraction in `answer_generation.parse`."""

    def test_markers_map_back_to_passage_source_ids(self):
        request = _request(PASSAGES)

        parsed = answer_generation.parse("Alpha is first [1]. Beta is second [2].", request)

        self.assertEqual(
            [citation["source_id"] for citation in parsed["citations"]],
            ["chunk-a", "chunk-b"],
        )
        self.assertEqual(parsed["invalid_citation_count"], 0)

    def test_markers_are_preserved_in_the_answer_text(self):
        request = _request(PASSAGES)

        parsed = answer_generation.parse("Alpha is first [1].", request)

        self.assertEqual(parsed["answer"], "Alpha is first [1].")

    def test_answer_without_markers_yields_empty_list_not_none(self):
        request = _request(PASSAGES)

        parsed = answer_generation.parse("Alpha is the first letter.", request)

        self.assertEqual(parsed["citations"], [])
        self.assertIsNotNone(parsed["citations"])

    def test_out_of_range_marker_is_discarded_and_counted(self):
        request = _request(PASSAGES)

        parsed = answer_generation.parse("Alpha [1]. Gamma [7].", request)

        # Not clamped onto passage 2: a clamped bad marker would count as a
        # correct citation in the precision numerator.
        self.assertEqual([c["source_id"] for c in parsed["citations"]], ["chunk-a"])
        self.assertEqual(parsed["invalid_citation_count"], 1)

    def test_repeated_marker_is_deduplicated_in_first_appearance_order(self):
        request = _request(PASSAGES)

        parsed = answer_generation.parse("Beta [2]. Alpha [1]. Beta again [2].", request)

        self.assertEqual([c["source_id"] for c in parsed["citations"]], ["chunk-b", "chunk-a"])

    def test_parser_without_request_reports_none_rather_than_guessing(self):
        parsed = answer_generation.parse("Alpha is first [1].")

        self.assertIsNone(parsed["citations"])

    def test_string_passages_yield_citations_without_source_ids(self):
        request = _request(["Alpha is the first letter."])

        parsed = answer_generation.parse("Alpha [1].", request)

        self.assertEqual(len(parsed["citations"]), 1)
        self.assertIsNone(parsed["citations"][0]["source_id"])

    def test_disabled_flag_returns_none_and_leaves_prompt_unnumbered(self):
        request = _request(PASSAGES)

        with patch.object(answer_generation, "_citations_enabled", return_value=False):
            parsed = answer_generation.parse("Alpha [1].", request)
            prompt = answer_generation.build_prompt(request)

        self.assertIsNone(parsed["citations"])
        self.assertNotIn("[1] Alpha is the first letter.", prompt.raw_prompt)

    def test_parsed_output_model_accepts_the_parser_result(self):
        request = _request(PASSAGES)

        parsed = answer_generation.parse("Alpha [1]. Gamma [7].", request)
        validated = AnswerGenerationParsedOutput.model_validate(parsed)

        self.assertEqual(validated.citations[0].source_id, "chunk-a")
        self.assertEqual(validated.invalid_citation_count, 1)


class AnswerCitationPromptTests(unittest.TestCase):
    """Prompt construction for citable answers."""

    def test_prompt_numbers_passages_and_asks_for_markers(self):
        prompt = answer_generation.build_prompt(_request(PASSAGES)).raw_prompt

        self.assertIn("[1] Alpha is the first letter.", prompt)
        self.assertIn("[2] Beta is the second letter.", prompt)
        self.assertIn("as [1], [2]", prompt)

    def test_prompt_keeps_the_brevity_constraint(self):
        prompt = answer_generation.build_prompt(_request(PASSAGES)).raw_prompt

        self.assertIn("1-3 short sentences", prompt)


class JudgeClaimNormalizationTests(unittest.TestCase):
    """Claim-level fields in `answer_evaluation._normalize_payload`."""

    def test_claims_are_normalized_and_unsupported_counted(self):
        normalized = _normalize_payload(
            {
                "verdict": "pass",
                "claims": [
                    {"claim": "Alpha is first", "supported": True, "supporting_passage_ids": [1]},
                    {"claim": "Alpha is purple", "supported": "false"},
                ],
                "hallucination_verdict": "minor",
            }
        )

        self.assertEqual(normalized["claims"][0]["supporting_passage_ids"], ["1"])
        self.assertFalse(normalized["claims"][1]["supported"])
        self.assertEqual(normalized["unsupported_claim_count"], 1)
        self.assertEqual(normalized["hallucination_verdict"], "minor")

    def test_alternate_key_spellings_are_tolerated(self):
        normalized = _normalize_payload(
            {
                "atomic_claims": [
                    {"text": "Alpha is first", "is_supported": True, "passage_ids": ["1"]}
                ],
                "hallucination": "HIGH",
            }
        )

        self.assertEqual(normalized["claims"][0]["claim"], "Alpha is first")
        self.assertEqual(normalized["hallucination_verdict"], "severe")

    def test_unknown_hallucination_verdict_is_unmeasured_not_none_verdict(self):
        normalized = _normalize_payload({"hallucination_verdict": "probably fine"})

        self.assertIsNone(normalized["hallucination_verdict"])

    def test_claim_without_text_is_dropped_rather_than_raising(self):
        normalized = _normalize_payload({"claims": [{"supported": True}, "Alpha is first"]})

        self.assertEqual(len(normalized["claims"]), 1)
        self.assertEqual(normalized["claims"][0]["claim"], "Alpha is first")

    def test_reported_count_used_only_when_no_claims_came_back(self):
        normalized = _normalize_payload({"unsupported_claim_count": "3"})

        self.assertEqual(normalized["unsupported_claim_count"], 3)

    def test_claim_list_wins_over_a_disagreeing_reported_count(self):
        normalized = _normalize_payload(
            {
                "unsupported_claim_count": 9,
                "claims": [{"claim": "Alpha is first", "supported": True}],
            }
        )

        self.assertEqual(normalized["unsupported_claim_count"], 0)


class JudgeFallbackTests(unittest.TestCase):
    """A malformed judge response must degrade, not raise."""

    def test_malformed_json_falls_back_to_defaults(self):
        result = parse_review("I think the answer looks fine, honestly.")

        self.assertEqual(result.payload["verdict"], "unavailable")
        self.assertEqual(result.payload["claims"], [])
        self.assertIsNone(result.payload["unsupported_claim_count"])
        self.assertIsNone(result.payload["hallucination_verdict"])

    def test_partial_json_keeps_missing_claim_fields_empty(self):
        result = parse_review('{"verdict":"pass","groundedness_score":0.9}')

        self.assertEqual(result.payload["claims"], [])
        self.assertIsNone(result.payload["hallucination_verdict"])


if __name__ == "__main__":
    unittest.main()
