"""Tests for the bounded ``claims`` array in the answer-review contract.

The unbounded array let the judge keep emitting claims until the
``ANSWER_EVALUATION_MAX_TOKENS`` ceiling truncated the JSON Schema output.
Bounding it at four claims keeps generations inside the budget.
"""
import unittest

from pydantic import ValidationError

from app.core.config import Settings
from app.llm.prompt_registry import PromptRegistry
from app.schemas.llm import AnswerReviewParsedOutput


def _claim(index: int):
    return {
        "claim": f"Claim {index}.",
        "supported": True,
        "supporting_passage_ids": [f"p{index}"],
    }


def _review(claim_count: int):
    return {
        "review_id": "review-1",
        "verdict": "pass",
        "groundedness_score": 0.9,
        "completeness_score": 0.8,
        "safety_score": 1.0,
        "issues": ["minor wording"],
        "claims": [_claim(i) for i in range(claim_count)],
        "unsupported_claim_count": 0,
        "hallucination_verdict": "none",
        "revision_applied": False,
        "model_name": "test-model",
        "created_at": 1730000000000,
    }


class AnswerReviewClaimBoundTests(unittest.TestCase):
    def test_json_schema_bounds_claims_at_four(self):
        schema = AnswerReviewParsedOutput.model_json_schema()
        self.assertEqual(schema["properties"]["claims"]["maxItems"], 4)

    def test_issues_remains_unbounded(self):
        schema = AnswerReviewParsedOutput.model_json_schema()
        self.assertNotIn("maxItems", schema["properties"]["issues"])

    def test_four_claims_validate(self):
        parsed = AnswerReviewParsedOutput.model_validate(_review(4))
        self.assertEqual(len(parsed.claims), 4)

    def test_five_claims_are_rejected(self):
        with self.assertRaises(ValidationError):
            AnswerReviewParsedOutput.model_validate(_review(5))

    def test_provider_schema_comes_from_the_model(self):
        registry = PromptRegistry(Settings())
        for version in ("answer_evaluation.v1", "answer_evaluation.v2"):
            entry = registry.resolve("answer_evaluation", version)
            self.assertIs(entry.output_model, AnswerReviewParsedOutput)
            self.assertEqual(
                entry.output_model.model_json_schema()["properties"]["claims"]["maxItems"],
                4,
            )


if __name__ == "__main__":
    unittest.main()
