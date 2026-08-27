"""Tests for the answer-evaluation judge contract and its fingerprint.

Two things must stay true together. The evaluator's *instruction* has to state
the same bound its *schema* enforces, or the judge silently drops claims and
the quality metrics move for a reason nobody recorded. And the schema has to
carry a deterministic fingerprint, or a benchmark run under the bounded
contract compares as identical to one run under the unbounded contract.
"""
import unittest

from app.core.config import Settings
from app.llm.prompt_registry import PromptRegistry
from app.schemas.llm import (
    AnswerEvaluationInput,
    AnswerEvaluationRequest,
    AnswerReviewParsedOutput,
    ClaimAssessment,
    answer_review_output_schema_sha256,
)
from app.llm.prompts.answer_evaluation import build_prompt_v2
from pydantic import BaseModel, ConfigDict, Field
from shared.schema_provenance import canonical_schema_sha256

from typing import List


def _evaluation_prompt() -> str:
    request = AnswerEvaluationRequest(
        request_type="answer_evaluation",
        metadata={},
        input=AnswerEvaluationInput(
            question="What is the retention period?",
            answer="Records are kept for seven years.",
            reference_context=["Records are retained for seven years."],
        ),
    )
    return build_prompt_v2(request).raw_prompt


class EvaluatorContractInstructionTests(unittest.TestCase):
    """The instruction must define the bound the schema enforces."""

    def test_claims_cap_remains_four(self):
        schema = AnswerReviewParsedOutput.model_json_schema()
        self.assertEqual(schema["properties"]["claims"]["maxItems"], 4)

    def test_instruction_states_the_four_claim_bound(self):
        prompt = _evaluation_prompt()
        self.assertIn("AT MOST 4 MATERIAL", prompt)
        self.assertIn('"claims": array of AT MOST 4 objects', prompt)

    def test_instruction_defines_the_selection_priority(self):
        prompt = _evaluation_prompt()
        self.assertIn("more than 4 atomic claims", prompt)
        self.assertIn(
            "1. claims that are unsupported or contradicted by the reference context;",
            prompt,
        )
        self.assertIn(
            "2. claims that materially affect the answer to the user's question;",
            prompt,
        )
        self.assertIn(
            "3. otherwise the most information-bearing distinct claims.",
            prompt,
        )
        self.assertIn("Do not spend a claim slot on a trivial restatement", prompt)

    def test_instruction_calls_the_array_a_bounded_sample(self):
        prompt = _evaluation_prompt()
        self.assertIn("bounded diagnostic sample", prompt)
        self.assertIn("not an exhaustive enumeration of every sentence", prompt)

    def test_instruction_scopes_unsupported_claim_count_to_reviewed_claims(self):
        """PART B: the count describes the sample, and says so."""
        prompt = _evaluation_prompt()
        self.assertIn(
            "counts the unsupported claims",
            prompt,
        )
        self.assertIn("it is not a count of every unsupported", prompt)

    def test_rubric_is_not_otherwise_redesigned(self):
        prompt = _evaluation_prompt()
        for unchanged in (
            '- "verdict": string',
            '- "groundedness_score": number',
            '- "completeness_score": number',
            '- "safety_score": number',
            '- "hallucination_verdict": one of "none", "minor", "severe"',
            '- "revision_applied": boolean',
        ):
            self.assertIn(unchanged, prompt)


class AnswerReviewSchemaShaTests(unittest.TestCase):
    """The fingerprint must be derived, stable, and constraint-sensitive."""

    def test_sha_is_derived_from_the_authoritative_model_schema(self):
        self.assertEqual(
            answer_review_output_schema_sha256(),
            canonical_schema_sha256(AnswerReviewParsedOutput.model_json_schema()),
        )

    def test_sha_is_a_sha256_hex_digest(self):
        digest = answer_review_output_schema_sha256()
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(char in "0123456789abcdef" for char in digest))

    def test_same_schema_hashes_the_same(self):
        self.assertEqual(
            answer_review_output_schema_sha256(),
            answer_review_output_schema_sha256(),
        )

    def test_key_order_does_not_change_the_hash(self):
        schema = AnswerReviewParsedOutput.model_json_schema()
        reordered = dict(reversed(list(schema.items())))
        self.assertEqual(
            canonical_schema_sha256(schema),
            canonical_schema_sha256(reordered),
        )

    def test_changing_max_items_changes_the_hash(self):
        class LooserAnswerReview(BaseModel):
            model_config = ConfigDict(extra="forbid", protected_namespaces=())

            claims: List[ClaimAssessment] = Field(default_factory=list, max_length=4)

        class LoosestAnswerReview(BaseModel):
            model_config = ConfigDict(extra="forbid", protected_namespaces=())

            claims: List[ClaimAssessment] = Field(default_factory=list, max_length=8)

        bounded = canonical_schema_sha256(LooserAnswerReview.model_json_schema())
        loosened = canonical_schema_sha256(LoosestAnswerReview.model_json_schema())
        self.assertNotEqual(bounded, loosened)

    def test_removing_the_bound_changes_the_hash(self):
        schema = AnswerReviewParsedOutput.model_json_schema()
        unbounded = {
            **schema,
            "properties": {
                **schema["properties"],
                "claims": {
                    key: value
                    for key, value in schema["properties"]["claims"].items()
                    if key != "maxItems"
                },
            },
        }
        self.assertNotEqual(
            canonical_schema_sha256(schema),
            canonical_schema_sha256(unbounded),
        )

    def test_sha_covers_the_schema_the_provider_is_actually_sent(self):
        """The digest and the invocation must read the same model."""
        registry = PromptRegistry(Settings())
        entry = registry.resolve("answer_evaluation", None)
        self.assertIs(entry.output_model, AnswerReviewParsedOutput)
        self.assertEqual(
            answer_review_output_schema_sha256(),
            canonical_schema_sha256(entry.output_model.model_json_schema()),
        )


if __name__ == "__main__":
    unittest.main()
