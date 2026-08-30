"""Focused contracts for the real cross-encoder reranker."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from app.services.conversation_stages import EXECUTION_PATHS
from app.services.learned_reranker import CrossEncoderReranker
from app.tests.eval._harness import FakeBackend, build, execute, fetch


class FakeCrossEncoder:
    def __init__(self, scores_by_passage):
        self.scores_by_passage = scores_by_passage
        self.calls = []

    def predict(self, pairs, **kwargs):
        self.calls.append((pairs, kwargs))
        return [self.scores_by_passage[passage] for _, passage in pairs]


def config(**overrides):
    values = {
        "reranker_enabled": True,
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "reranker_model_revision": "pinned-test-revision",
        "reranker_candidate_k": 2,
        "reranker_timeout_seconds": 0.2,
        "reranker_batch_size": 4,
        "reranker_max_length": 128,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_cross_encoder_reranks_only_the_bound_and_preserves_retrieval_scores():
    model = FakeCrossEncoder({"weak": 0.1, "answer": 0.9})
    reranker = CrossEncoderReranker(config(), model_factory=lambda *_: model)

    result = asyncio.run(
        reranker.rerank(
            "question",
            [
                {"chunk_id": "c1", "text": "weak", "score": 0.91},
                {"chunk_id": "c2", "text": "answer", "score": 0.22},
                {"chunk_id": "c3", "text": "outside-bound", "score": 0.1},
            ],
        )
    )

    assert result.status == "success"
    assert result.candidate_count == 2
    assert [item["chunk_id"] for item in result.candidates] == ["c2", "c1"]
    assert result.candidates[0]["retrieval_score"] == 0.22
    assert result.candidates[0]["reranker_score"] == pytest.approx(0.9)
    assert len(model.calls[0][0]) == 2


def test_timeout_falls_back_to_the_original_bounded_order():
    class SlowModel:
        def predict(self, pairs, **kwargs):
            time.sleep(0.05)
            return [0.1, 0.9]

    reranker = CrossEncoderReranker(
        config(reranker_timeout_seconds=0.001),
        model_factory=lambda *_: SlowModel(),
    )
    candidates = [
        {"chunk_id": "c1", "text": "first", "score": 0.8},
        {"chunk_id": "c2", "text": "second", "score": 0.2},
        {"chunk_id": "c3", "text": "outside", "score": 0.1},
    ]

    result = asyncio.run(reranker.rerank("question", candidates))

    assert result.status == "timeout"
    assert [item["chunk_id"] for item in result.candidates] == ["c1", "c2"]
    assert all("reranker_score" not in item for item in result.candidates)


def test_both_conversation_modes_rerank_before_generation():
    regular = EXECUTION_PATHS["regular"]
    extended = EXECUTION_PATHS["extended"]

    assert regular.index("retrieve_chunks_once") < regular.index("rerank_candidates")
    assert regular.index("rerank_candidates") < regular.index("generate_answer")
    assert extended.index("merge_candidates") < extended.index("rerank_candidates")
    assert extended.index("rerank_candidates") < extended.index("generate_draft_answer")


def test_retrieval_eval_scores_the_learned_order_and_records_lineage():
    backend = FakeBackend(
        {
            "first": {
                "chunks": [
                    {"chunk_id": "c1", "text": "weak", "score": 0.9},
                    {"chunk_id": "c9", "text": "answer", "score": 0.2},
                ]
            }
        }
    )
    store, runner, _, dataset_id = build(
        items=[{"query": "first", "relevant_chunk_ids": ["c9"]}],
        backend=backend,
    )
    model = FakeCrossEncoder({"weak": 0.05, "answer": 0.95})
    runner.reranker = CrossEncoderReranker(
        config(reranker_candidate_k=20), model_factory=lambda *_: model
    )

    run = execute(runner, dataset_id)
    row = fetch(store, run["run_id"])["per_item"][0]
    reranked = next(
        stage
        for stage in row["retrieval_trace"]["stages"]
        if stage["stage"] == "reranked"
    )

    assert row["first_hit_rank"] == 1
    assert row["reciprocal_rank"] == pytest.approx(1.0)
    assert reranked["candidates"][0] == {
        "rank": 1,
        "chunk_id": "c9",
        "file_id": None,
        "score": 0.2,
        "reranker_score": pytest.approx(0.95),
    }
