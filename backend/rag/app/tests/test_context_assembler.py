"""Focused RAG-03 final-context assembly tests."""
from app.services.context_assembler import (
    assemble_context,
    context_token_count,
    passage_token_cost,
)


def chunk(chunk_id, text, score, source):
    return {"chunk_id": chunk_id, "text": text, "score": score, "source": source}


def assemble(candidates, budget=200, limit=6, tolerance=0.08):
    return assemble_context(
        candidates,
        token_budget=budget,
        max_passages=limit,
        diversity_score_tolerance=tolerance,
    )


def test_context_never_exceeds_exact_budget_boundary():
    candidate = chunk("c1", "boundary evidence", 0.9, "a.md")
    exact = passage_token_cost(candidate, 1)

    selected = assemble([candidate], budget=exact)

    assert [item["chunk_id"] for item in selected] == ["c1"]
    assert context_token_count(selected) == exact


def test_oversized_chunk_is_deterministically_truncated_to_budget():
    selected = assemble([chunk("large", "evidence " * 500, 0.9, "a.md")], budget=40)

    assert [item["chunk_id"] for item in selected] == ["large"]
    assert selected[0]["context_truncated"] is True
    assert context_token_count(selected) <= 40


def test_empty_context_is_stable():
    assert assemble([]) == []
    assert assemble([{"chunk_id": "empty", "text": ""}]) == []


def test_selection_and_order_are_deterministic():
    candidates = [
        chunk("a", "alpha evidence", 0.8, "one.md"),
        chunk("b", "beta evidence", 0.8, "two.md"),
        chunk("c", "gamma evidence", 0.7, "three.md"),
    ]

    first = assemble(candidates)
    second = assemble(candidates)

    assert [item["chunk_id"] for item in first] == ["a", "b", "c"]
    assert first == second


def test_duplicate_and_redundant_chunks_do_not_waste_budget():
    repeated = "the same five word evidence appears in both chunks"
    candidates = [
        chunk("a", repeated, 0.9, "one.md"),
        chunk("a", "duplicate id with different text", 0.89, "one.md"),
        chunk("b", repeated.upper(), 0.88, "two.md"),
        chunk("c", "distinct useful evidence", 0.8, "three.md"),
    ]

    assert [item["chunk_id"] for item in assemble(candidates)] == ["a", "c"]


def test_comparable_scores_prefer_a_new_document():
    candidates = [
        chunk("a1", "best evidence", 0.90, "one.md"),
        chunk("a2", "similar-score continuation", 0.87, "one.md"),
        chunk("b1", "other document evidence", 0.85, "two.md"),
    ]

    assert [item["chunk_id"] for item in assemble(candidates, limit=2)] == ["a1", "b1"]


def test_clearly_stronger_chunk_is_not_displaced_for_diversity():
    candidates = [
        chunk("a1", "best evidence", 0.95, "one.md"),
        chunk("a2", "strong continuation", 0.84, "one.md"),
        chunk("b1", "weaker other document", 0.70, "two.md"),
    ]

    assert [item["chunk_id"] for item in assemble(candidates, limit=2)] == ["a1", "a2"]
