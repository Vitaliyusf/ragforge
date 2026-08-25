"""Hand-computable tests for the citation precision/recall conventions.

Every expected value here is arithmetic a reader can check without running
anything, which is the point: these are the numbers the Quality panel puts in
front of an operator.
"""
import unittest

from app.services.citation_metrics import (
    aggregate_mean,
    citation_f1,
    citation_precision,
    citation_recall,
    cited_chunk_ratio,
    supporting_passage_ids,
)


class CitationPrecisionTests(unittest.TestCase):
    """Of the passages the answer cited, how many actually support a claim."""

    def test_all_citations_supported_scores_one(self):
        self.assertEqual(citation_precision(["a", "b"], {"a", "b", "c"}), 1.0)

    def test_half_the_citations_supported_scores_one_half(self):
        self.assertEqual(citation_precision(["a", "b"], {"a"}), 0.5)

    def test_no_citations_supported_scores_zero(self):
        self.assertEqual(citation_precision(["a", "b"], {"c"}), 0.0)

    def test_zero_citations_is_none_not_zero(self):
        # "Did not cite" and "cited badly" are different failures. A 0.0 here
        # would average them together.
        self.assertIsNone(citation_precision([], {"a"}))

    def test_duplicate_citations_are_counted_once(self):
        # Two markers, one distinct passage, both supported.
        self.assertEqual(citation_precision(["a", "a"], {"a"}), 1.0)
        # Two distinct passages, one supported, with the bad one repeated.
        self.assertEqual(citation_precision(["a", "b", "b"], {"a"}), 0.5)

    def test_no_supporting_passages_scores_zero_when_something_was_cited(self):
        self.assertEqual(citation_precision(["a"], set()), 0.0)


class CitationRecallTests(unittest.TestCase):
    """Of the claims the context could support, how many were credited."""

    def test_every_supportable_claim_cited_scores_one(self):
        claims = [
            {"claim": "x", "supported": True, "supporting_passage_ids": ["a"]},
            {"claim": "y", "supported": True, "supporting_passage_ids": ["b"]},
        ]

        self.assertEqual(citation_recall(claims, {"a", "b"}), 1.0)

    def test_half_the_supportable_claims_cited_scores_one_half(self):
        claims = [
            {"claim": "x", "supported": True, "supporting_passage_ids": ["a"]},
            {"claim": "y", "supported": True, "supporting_passage_ids": ["b"]},
        ]

        self.assertEqual(citation_recall(claims, {"a"}), 0.5)

    def test_unsupported_claims_are_outside_the_denominator(self):
        claims = [
            {"claim": "x", "supported": True, "supporting_passage_ids": ["a"]},
            {"claim": "y", "supported": False, "supporting_passage_ids": []},
        ]

        # One supportable claim, cited: 1.0, not 0.5. An unsupported claim
        # cannot be credited to a source and must not depress recall.
        self.assertEqual(citation_recall(claims, {"a"}), 1.0)

    def test_zero_supportable_claims_is_none(self):
        claims = [{"claim": "y", "supported": False, "supporting_passage_ids": []}]

        self.assertIsNone(citation_recall(claims, {"a"}))

    def test_empty_claim_list_is_none(self):
        self.assertIsNone(citation_recall([], {"a"}))

    def test_supported_claim_without_passage_ids_is_not_supportable(self):
        claims = [{"claim": "x", "supported": True, "supporting_passage_ids": []}]

        self.assertIsNone(citation_recall(claims, {"a"}))

    def test_claim_counts_as_credited_when_any_of_its_passages_is_cited(self):
        claims = [{"claim": "x", "supported": True, "supporting_passage_ids": ["a", "b"]}]

        self.assertEqual(citation_recall(claims, {"b"}), 1.0)

    def test_falls_back_to_the_claims_own_cited_flag(self):
        claims = [
            {"claim": "x", "supported": True, "supporting_passage_ids": ["a"], "cited": True},
            {"claim": "y", "supported": True, "supporting_passage_ids": ["b"], "cited": False},
        ]

        self.assertEqual(citation_recall(claims), 0.5)


class CitationF1Tests(unittest.TestCase):
    """The harmonic mean, and what it does with an unmeasured half."""

    def test_harmonic_mean(self):
        self.assertEqual(citation_f1(1.0, 1.0), 1.0)
        self.assertAlmostEqual(citation_f1(0.5, 1.0), 2 / 3)

    def test_both_zero_is_zero_not_a_division_error(self):
        self.assertEqual(citation_f1(0.0, 0.0), 0.0)

    def test_an_unmeasured_half_makes_the_f1_unmeasured(self):
        self.assertIsNone(citation_f1(None, 1.0))
        self.assertIsNone(citation_f1(1.0, None))


class SupportingIdsTests(unittest.TestCase):
    """Extracting the judge-confirmed support set from a claim list."""

    def test_only_supported_claims_contribute_ids(self):
        claims = [
            {"claim": "x", "supported": True, "supporting_passage_ids": ["a"]},
            {"claim": "y", "supported": False, "supporting_passage_ids": ["b"]},
        ]

        self.assertEqual(supporting_passage_ids(claims), {"a"})

    def test_malformed_entries_are_ignored(self):
        self.assertEqual(supporting_passage_ids([None, "x", {}]), set())


class CitedChunkRatioTests(unittest.TestCase):
    """Share of the retrieved chunks the answer actually cited."""

    def test_ratio_over_retrieved_chunks(self):
        self.assertEqual(cited_chunk_ratio(["a", "b"], 4), 0.5)

    def test_duplicate_citations_counted_once(self):
        self.assertEqual(cited_chunk_ratio(["a", "a"], 4), 0.25)

    def test_no_retrieved_chunks_is_none(self):
        self.assertIsNone(cited_chunk_ratio(["a"], 0))

    def test_ratio_is_capped_at_one(self):
        # A citation to a passage outside the retrieved set should never make
        # the answer look like it cited more chunks than existed.
        self.assertEqual(cited_chunk_ratio(["a", "b", "c"], 2), 1.0)


class AggregateMeanTests(unittest.TestCase):
    """Means that exclude unmeasured values and say how many they excluded."""

    def test_mean_excludes_none_and_reports_the_count(self):
        self.assertEqual(
            aggregate_mean([1.0, None, 0.5, None]),
            {"mean": 0.75, "counted": 2, "excluded": 2},
        )

    def test_all_none_yields_a_none_mean(self):
        self.assertEqual(
            aggregate_mean([None, None]),
            {"mean": None, "counted": 0, "excluded": 2},
        )

    def test_empty_input_yields_a_none_mean(self):
        self.assertEqual(aggregate_mean([]), {"mean": None, "counted": 0, "excluded": 0})


if __name__ == "__main__":
    unittest.main()
