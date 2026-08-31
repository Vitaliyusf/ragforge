"""CONC-05: concurrency must not change what the reranker returns.

Before this task the reranker was single-flight: a request arriving while
another was already scoring got ``busy`` and its pipeline fell back to the
fused RRF ordering. The same query over the same corpus therefore produced a
different final ranking depending on who else happened to be reranking. These
tests pin the replacement — bounded queueing, exact result ownership, and
``busy`` reserved for real overload.
"""
from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Iterator, List, Tuple

import pytest

from app.core.config import RAGConfig
from app.services.learned_reranker import CrossEncoderReranker
from app.services.rerank_scheduler import (
    CLASS_BACKGROUND,
    CLASS_LIVE,
    RerankScheduler,
    RerankSchedulerClosed,
    RerankSchedulerOverloaded,
)

# Deterministic, content-derived scores. A pair's score depends on *both* its
# query and its passage, so a request that received a neighbour's slice cannot
# accidentally look correct.
_QUERY_WEIGHT = {"alpha": 100.0, "beta": 200.0, "question": 300.0}
_PASSAGE_SCORE = {
    "weak": 1.0,
    "answer": 9.0,
    "middle": 5.0,
    "outside-bound": 0.5,
    "dup": 7.0,
    "other": 3.0,
}


def test_production_defaults_bound_the_measured_cpu_operational_envelope():
    settings = RAGConfig()

    assert settings.reranker_candidate_k == 20
    assert settings.reranker_inference_workers == 2
    assert settings.reranker_max_batch_pairs == 20
    assert settings.reranker_microbatch_window_ms == 0.0
    assert settings.reranker_max_pending_pairs == 40
    assert settings.reranker_admission_timeout_seconds == 0.5
    assert settings.reranker_timeout_seconds == 12.0


def score_of(query: str, passage: str) -> float:
    return _QUERY_WEIGHT.get(query, 0.0) + _PASSAGE_SCORE.get(passage, 0.0)


def config(**overrides):
    values = {
        "service_name": "rag",
        "reranker_enabled": True,
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "reranker_model_revision": "pinned-test-revision",
        "reranker_candidate_k": 20,
        "reranker_timeout_seconds": 2.0,
        "reranker_batch_size": 4,
        "reranker_max_length": 128,
        "reranker_microbatch_window_ms": 20.0,
        "reranker_max_batch_pairs": 64,
        "reranker_max_pending_pairs": 512,
        "reranker_admission_timeout_seconds": 1.0,
        "reranker_inference_workers": 2,
        "reranker_max_background_inflight": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ScoringModel:
    """A CrossEncoder stand-in that records every physical forward pass."""

    def __init__(self, *, delay: float = 0.0, fail: bool = False, drop: int = 0) -> None:
        self.delay = delay
        self.fail = fail
        # How many scores to omit, to exercise the count-mismatch contract.
        self.drop = drop
        self.calls: List[List[Tuple[str, str]]] = []
        self._lock = threading.Lock()

    def predict(self, pairs, **_kwargs):
        with self._lock:
            self.calls.append(list(pairs))
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("model exploded")
        scores = [score_of(query, passage) for query, passage in pairs]
        return scores[: len(scores) - self.drop] if self.drop else scores

    @property
    def batch_sizes(self) -> List[int]:
        with self._lock:
            return [len(call) for call in self.calls]


class GatedPredict:
    """A predict callable whose first call blocks until explicitly released.

    Holding one forward pass open is how these tests create *real* contention
    deterministically, without sleeping and hoping.
    """

    def __init__(self) -> None:
        self.calls: List[List[Tuple[str, str]]] = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()

    def __call__(self, pairs: List[Tuple[str, str]]) -> List[float]:
        with self._lock:
            self.calls.append(list(pairs))
            first = len(self.calls) == 1
        if first:
            self.entered.set()
            self.release.wait(5.0)
        return [score_of(query, passage) for query, passage in pairs]

    @property
    def batch_sizes(self) -> List[int]:
        with self._lock:
            return [len(call) for call in self.calls]


class AllGatedPredict:
    """Block every physical call so outstanding capacity is deterministic."""

    def __init__(self) -> None:
        self.calls: List[List[Tuple[str, str]]] = []
        self.release = threading.Event()
        self._condition = threading.Condition()

    def __call__(self, pairs: List[Tuple[str, str]]) -> List[float]:
        with self._condition:
            self.calls.append(list(pairs))
            self._condition.notify_all()
        self.release.wait(5.0)
        return [score_of(query, passage) for query, passage in pairs]

    def wait_for_calls(self, count: int) -> None:
        with self._condition:
            assert self._condition.wait_for(
                lambda: len(self.calls) >= count, timeout=5.0
            )


def candidates(*names: str, base: float = 0.9) -> List[dict]:
    """Candidates in a deliberately *wrong* retrieval order, best-scored last."""
    return [
        {"chunk_id": f"c{index}", "text": name, "score": base - index * 0.1}
        for index, name in enumerate(names)
    ]


@contextmanager
def scheduler(predict, **overrides) -> Iterator[RerankScheduler]:
    settings = {
        "service": "rag",
        "max_batch_pairs": 8,
        "microbatch_window_ms": 25.0,
        "max_pending_pairs": 64,
        "admission_timeout_seconds": 1.0,
        "inference_workers": 2,
    }
    settings.update(overrides)
    instance = RerankScheduler(predict, **settings).start()
    try:
        yield instance
    finally:
        instance.shutdown(timeout=5.0)


@contextmanager
def reranker(model, **overrides) -> Iterator[CrossEncoderReranker]:
    instance = CrossEncoderReranker(config(**overrides), model_factory=lambda *_: model)
    try:
        yield instance
    finally:
        instance.shutdown(timeout=5.0)


async def scores_of(future) -> List[float]:
    return await asyncio.wrap_future(future)


# ---------------------------------------------------------------------------
# 1-2. Concurrency queues; it does not degrade
# ---------------------------------------------------------------------------


def test_two_concurrent_requests_both_get_learned_reranking():
    """The defect this task exists to remove, stated directly."""
    model = ScoringModel(delay=0.05)

    async def main():
        with reranker(model) as instance:
            return await asyncio.gather(
                instance.rerank("alpha", candidates("weak", "answer", "middle")),
                instance.rerank("alpha", candidates("weak", "answer", "middle")),
            )

    first, second = asyncio.run(main())

    assert [first.status, second.status] == ["success", "success"]
    order = ["c1", "c2", "c0"]  # answer > middle > weak
    assert [item["chunk_id"] for item in first.candidates] == order
    assert [item["chunk_id"] for item in second.candidates] == order


@pytest.mark.parametrize("concurrency", [2, 4, 8])
def test_normal_contention_never_reports_busy(concurrency: int):
    """Admissible concurrency produces queueing, never a quality fallback."""
    model = ScoringModel(delay=0.02)

    async def main():
        with reranker(model) as instance:
            return await asyncio.gather(
                *(
                    instance.rerank("alpha", candidates("weak", "answer", "middle"))
                    for _ in range(concurrency)
                )
            )

    results = asyncio.run(main())

    assert {result.status for result in results} == {"success"}
    assert all("reranker_score" in item for result in results for item in result.candidates)


def test_concurrency_does_not_change_the_selected_ordering():
    """The quality gate: same query, same corpus, same answer under load."""
    model = ScoringModel()
    cands = candidates("weak", "answer", "middle", "other")

    async def alone():
        with reranker(model) as instance:
            return await instance.rerank("alpha", cands)

    async def contended():
        with reranker(ScoringModel(delay=0.02)) as instance:
            return await asyncio.gather(
                *(instance.rerank("alpha", cands) for _ in range(8))
            )

    uncontended = asyncio.run(alone())
    under_load = asyncio.run(contended())

    expected = [item["chunk_id"] for item in uncontended.candidates]
    for result in under_load:
        assert [item["chunk_id"] for item in result.candidates] == expected
        assert [item["reranker_score"] for item in result.candidates] == [
            item["reranker_score"] for item in uncontended.candidates
        ]


# ---------------------------------------------------------------------------
# 3-4. The scheduler stays bounded
# ---------------------------------------------------------------------------


def test_pending_capacity_is_bounded_and_refuses_typed():
    gate = GatedPredict()

    async def main():
        with scheduler(
            gate,
            max_batch_pairs=8,
            max_pending_pairs=4,
            admission_timeout_seconds=0.05,
            inference_workers=1,
            inference_slot_pairs=8,
        ) as instance:
            running = await instance.submit("alpha", ["weak", "answer"])
            gate.entered.wait(5.0)
            # Four pairs fit the bound; the fifth cannot be admitted while the
            # only worker is held, so it is refused rather than queued forever.
            queued = [
                await instance.submit("alpha", ["weak", "answer"]) for _ in range(2)
            ]
            assert instance.pending_pairs() == 4
            with pytest.raises(RerankSchedulerOverloaded) as refused:
                await instance.submit("alpha", ["middle"])
            gate.release.set()
            await asyncio.gather(scores_of(running), *(scores_of(f) for f in queued))
            return refused.value

    overloaded = asyncio.run(main())
    assert overloaded.reason == "saturated"
    assert overloaded.pool == "reranker_inference"


def test_pending_capacity_may_be_smaller_than_physical_batch_capacity():
    gate = GatedPredict()
    passages = ["weak", "answer"] * 10

    async def main():
        with scheduler(
            gate,
            max_batch_pairs=64,
            max_pending_pairs=40,
            inference_workers=1,
        ) as instance:
            running = await instance.submit("alpha", passages)
            gate.entered.wait(5.0)
            queued = [await instance.submit("alpha", passages) for _ in range(2)]
            assert instance.pending_pairs() == 40
            gate.release.set()
            await asyncio.gather(scores_of(running), *(scores_of(f) for f in queued))

    asyncio.run(main())

    assert max(gate.batch_sizes) == 40


def test_outstanding_capacity_sheds_work_beyond_supported_logical_envelope():
    gate = AllGatedPredict()
    passages = ["weak", "answer"] * 10

    async def main():
        with scheduler(
            gate,
            max_batch_pairs=64,
            max_pending_pairs=40,
            admission_timeout_seconds=0.05,
            inference_workers=2,
            inference_slot_pairs=20,
        ) as instance:
            running = [await instance.submit("alpha", passages)]
            await asyncio.to_thread(gate.wait_for_calls, 1)
            running.append(await instance.submit("alpha", passages))
            await asyncio.to_thread(gate.wait_for_calls, 2)
            with pytest.raises(RerankSchedulerOverloaded) as refused:
                await instance.submit("alpha", passages)

            gate.release.set()
            await asyncio.gather(*(scores_of(future) for future in running))

            # Completion restores the full live envelope without waiting for
            # the admission timeout to expire.
            recovered = await instance.submit("alpha", passages)
            await scores_of(recovered)
            return refused.value, instance.pending_pairs()

    overloaded, pending = asyncio.run(main())

    assert overloaded.reason == "saturated"
    assert pending == 0


def test_cancelling_queued_live_work_releases_outstanding_capacity():
    gate = AllGatedPredict()
    passages = ["weak", "answer"] * 5

    async def main():
        with scheduler(
            gate,
            max_batch_pairs=20,
            max_pending_pairs=40,
            admission_timeout_seconds=0.05,
            inference_workers=2,
            inference_slot_pairs=20,
        ) as instance:
            running = [await instance.submit("alpha", passages) for _ in range(2)]
            await asyncio.to_thread(gate.wait_for_calls, 2)
            queued = [await instance.submit("alpha", passages) for _ in range(2)]

            assert instance.pending_pairs() == 20
            assert queued[0].cancel() is True
            replacement = await instance.submit("alpha", passages)
            assert instance.pending_pairs() == 20

            gate.release.set()
            await asyncio.gather(
                *(scores_of(future) for future in running),
                scores_of(queued[1]),
                scores_of(replacement),
            )
            return instance.pending_pairs()

    assert asyncio.run(main()) == 0


def test_physical_batch_size_is_bounded():
    gate = GatedPredict()

    async def main():
        with scheduler(
            gate, max_batch_pairs=4, max_pending_pairs=64, inference_workers=1
        ) as instance:
            held = await instance.submit("alpha", ["weak", "answer"])
            gate.entered.wait(5.0)
            queued = [
                await instance.submit("alpha", ["weak", "answer", "middle"])
                for _ in range(4)
            ]
            gate.release.set()
            await asyncio.gather(scores_of(held), *(scores_of(f) for f in queued))

    asyncio.run(main())

    assert gate.calls, "no forward pass ran"
    # Three-pair requests are never split, and two never share a four-pair
    # batch, so every physical call is exactly one request's worth here.
    assert max(gate.batch_sizes) <= 4


def test_a_request_larger_than_one_batch_is_refused_and_never_widens_a_bound():
    """A single request may not exceed the configured hard bounds.

    `max_batch_pairs` is physical: no forward pass may carry more pairs than
    it, and a request is never split. A five-pair request under a four-pair
    batch bound therefore has no admissible shape. It must be refused typed —
    not admitted as one oversized forward pass, and not by letting it enlarge
    the pending queue it could not fit.
    """
    gate = GatedPredict()

    async def main():
        with scheduler(
            gate,
            max_batch_pairs=4,
            max_pending_pairs=8,
            admission_timeout_seconds=0.05,
            inference_workers=1,
        ) as instance:
            with pytest.raises(RerankSchedulerOverloaded) as refused:
                await instance.submit(
                    "alpha", ["weak", "answer", "middle", "other", "dup"]
                )
            # The refusal is immediate and leaves no residue in the queue.
            assert instance.pending_pairs() == 0

            # The pending bound is still the configured 8, not the 5 the
            # rejected request would have needed: one held request plus two
            # queued fill it exactly, and the next pair is ordinary overload.
            held = await instance.submit("alpha", ["weak", "answer", "middle", "other"])
            gate.entered.wait(5.0)
            queued = [
                await instance.submit(
                    "alpha", ["weak", "answer", "middle", "other"]
                )
                for _ in range(2)
            ]
            assert instance.pending_pairs() == 8
            with pytest.raises(RerankSchedulerOverloaded) as saturated:
                await instance.submit("alpha", ["middle"])
            gate.release.set()
            await asyncio.gather(scores_of(held), *(scores_of(f) for f in queued))
            return refused.value, saturated.value

    oversized, saturated = asyncio.run(main())

    assert oversized.reason == "oversized"
    assert oversized.pool == "reranker_inference"
    # Overload from load stays a distinct, separately actionable reason.
    assert saturated.reason == "saturated"

    # The model never saw the rejected request: no five-pair call, and none of
    # its pairs reached a forward pass at all.
    assert gate.calls, "no forward pass ran"
    assert max(gate.batch_sizes) <= 4
    assert all(len(call) != 5 for call in gate.calls)


def test_concurrent_requests_share_one_physical_forward_pass():
    """Micro-batching actually combines work, not just serialises it."""
    gate = GatedPredict()

    async def main():
        with scheduler(
            gate, max_batch_pairs=16, microbatch_window_ms=50.0, inference_workers=1
        ) as instance:
            held = await instance.submit("alpha", ["weak"])
            gate.entered.wait(5.0)
            queued = [
                await instance.submit("beta", ["answer", "middle"]) for _ in range(3)
            ]
            gate.release.set()
            await asyncio.gather(scores_of(held), *(scores_of(f) for f in queued))

    asyncio.run(main())

    assert gate.batch_sizes[0] == 1  # the held request ran alone
    assert max(gate.batch_sizes[1:]) > 2  # the three that queued combined


# ---------------------------------------------------------------------------
# 5-8. Result ownership
# ---------------------------------------------------------------------------


def test_batched_requests_receive_exactly_their_own_scores():
    gate = GatedPredict()

    async def main():
        with scheduler(
            gate, max_batch_pairs=16, microbatch_window_ms=50.0, inference_workers=1
        ) as instance:
            held = await instance.submit("question", ["other"])
            gate.entered.wait(5.0)
            left = await instance.submit("alpha", ["weak", "answer"])
            right = await instance.submit("beta", ["middle", "answer", "weak"])
            gate.release.set()
            return await asyncio.gather(
                scores_of(held), scores_of(left), scores_of(right)
            )

    held, left, right = asyncio.run(main())

    assert held == [score_of("question", "other")]
    assert left == [score_of("alpha", "weak"), score_of("alpha", "answer")]
    assert right == [
        score_of("beta", "middle"),
        score_of("beta", "answer"),
        score_of("beta", "weak"),
    ]


def test_duplicate_candidate_texts_keep_distinct_positions():
    model = ScoringModel()

    async def main():
        with reranker(model) as instance:
            return await instance.rerank(
                "alpha", candidates("dup", "other", "dup", "answer")
            )

    result = asyncio.run(main())

    assert result.status == "success"
    assert result.candidate_count == 4
    # Both duplicates survive as separate candidates, each carrying its own
    # score, and the deterministic tie-break keeps their input order.
    assert [item["chunk_id"] for item in result.candidates] == ["c3", "c0", "c2", "c1"]
    duplicates = [item for item in result.candidates if item["text"] == "dup"]
    assert [item["chunk_id"] for item in duplicates] == ["c0", "c2"]
    assert {item["reranker_score"] for item in duplicates} == {score_of("alpha", "dup")}


def test_a_cancelled_request_cannot_shift_a_neighbours_scores():
    gate = GatedPredict()

    async def main():
        with scheduler(
            gate, max_batch_pairs=16, microbatch_window_ms=50.0, inference_workers=1
        ) as instance:
            held = await instance.submit("question", ["other"])
            gate.entered.wait(5.0)
            abandoned = await instance.submit("alpha", ["weak", "answer"])
            survivor = await instance.submit("beta", ["middle", "answer"])
            assert abandoned.cancel()
            gate.release.set()
            return await asyncio.gather(scores_of(held), scores_of(survivor))

    held, survivor = asyncio.run(main())

    assert held == [score_of("question", "other")]
    assert survivor == [score_of("beta", "middle"), score_of("beta", "answer")]
    # The cancelled request's two pairs never entered a forward pass.
    assert sum(gate.batch_sizes) == 3


def test_a_failed_forward_pass_completes_every_affected_waiter():
    model = ScoringModel(fail=True, delay=0.02)

    async def main():
        with reranker(model) as instance:
            return await asyncio.gather(
                *(
                    instance.rerank("alpha", candidates("weak", "answer"))
                    for _ in range(4)
                )
            )

    results = asyncio.run(main())

    assert {result.status for result in results} == {"error"}
    # Fallback is the bounded input order, unscored — never a partial ranking.
    for result in results:
        assert [item["chunk_id"] for item in result.candidates] == ["c0", "c1"]
        assert all("reranker_score" not in item for item in result.candidates)


def test_a_score_count_mismatch_fails_the_affected_request():
    model = ScoringModel(drop=1)

    async def main():
        with reranker(model) as instance:
            return await instance.rerank("alpha", candidates("weak", "answer"))

    result = asyncio.run(main())

    assert result.status == "error"
    assert all("reranker_score" not in item for item in result.candidates)


# ---------------------------------------------------------------------------
# 9-10. Overload and timeout
# ---------------------------------------------------------------------------


def test_explicit_overload_keeps_the_documented_busy_fallback():
    """`busy` survives, but only as real overload."""
    model = ScoringModel(delay=0.3)

    async def main():
        with reranker(
            model,
            reranker_max_batch_pairs=2,
            reranker_max_pending_pairs=2,
            reranker_admission_timeout_seconds=0.01,
            reranker_inference_workers=1,
            reranker_max_background_inflight=1,
        ) as instance:
            return await asyncio.gather(
                *(
                    instance.rerank("alpha", candidates("weak", "answer"))
                    for _ in range(6)
                )
            )

    results = asyncio.run(main())
    statuses = [result.status for result in results]

    assert "busy" in statuses
    for result, status in zip(results, statuses):
        if status != "busy":
            continue
        assert [item["chunk_id"] for item in result.candidates] == ["c0", "c1"]
        assert all("reranker_score" not in item for item in result.candidates)


def test_a_timeout_releases_capacity_for_the_next_request():
    model = ScoringModel(delay=0.15)

    async def main():
        with reranker(model, reranker_timeout_seconds=0.01) as instance:
            timed_out = await instance.rerank("alpha", candidates("weak", "answer"))
            instance.timeout_seconds = 5.0
            recovered = await instance.rerank("alpha", candidates("weak", "answer"))
            return timed_out, recovered, instance.scheduler.pending_pairs()

    timed_out, recovered, pending = asyncio.run(main())

    assert timed_out.status == "timeout"
    assert recovered.status == "success"
    assert pending == 0


# ---------------------------------------------------------------------------
# 11. Fairness
# ---------------------------------------------------------------------------


def test_live_work_progresses_while_background_load_runs():
    model = ScoringModel(delay=0.05)
    started = threading.Event()

    async def main():
        with reranker(model) as instance:

            async def background():
                for _ in range(12):
                    started.set()
                    await instance.rerank(
                        "beta",
                        candidates("weak", "answer", "middle"),
                        traffic_class="eval",
                    )

            flood = [asyncio.create_task(background()) for _ in range(3)]
            await asyncio.sleep(0.05)
            assert started.is_set()
            live = await asyncio.gather(
                *(
                    instance.rerank("alpha", candidates("weak", "answer"))
                    for _ in range(4)
                )
            )
            await asyncio.gather(*flood)
            return live

    live = asyncio.run(main())

    # Live never degrades under sustained background load, and background is
    # still allowed to finish — it is a reservation, not a lockout.
    assert {result.status for result in live} == {"success"}


def test_background_may_not_occupy_every_inference_worker():
    gate = GatedPredict()

    async def main():
        with scheduler(
            gate, inference_workers=2, max_background_inflight=1, max_batch_pairs=2
        ) as instance:
            held = await instance.submit(
                "beta", ["weak", "answer"], scheduling_class=CLASS_BACKGROUND
            )
            gate.entered.wait(5.0)
            queued = await instance.submit(
                "beta", ["middle", "other"], scheduling_class=CLASS_BACKGROUND
            )
            # One background batch is running and the second is parked, so the
            # free worker belongs to live work.
            live = await instance.submit(
                "alpha", ["answer"], scheduling_class=CLASS_LIVE
            )
            result = await asyncio.wait_for(scores_of(live), 5.0)
            assert instance.background_inflight == 1
            gate.release.set()
            await asyncio.gather(scores_of(held), scores_of(queued))
            return result

    assert asyncio.run(main()) == [score_of("alpha", "answer")]


# ---------------------------------------------------------------------------
# 12. Shutdown
# ---------------------------------------------------------------------------


def test_shutdown_without_draining_fails_pending_waiters_explicitly():
    gate = GatedPredict()

    async def main():
        instance = RerankScheduler(
            gate,
            service="rag",
            max_batch_pairs=2,
            microbatch_window_ms=5.0,
            max_pending_pairs=64,
            admission_timeout_seconds=1.0,
            inference_workers=1,
        ).start()
        held = await instance.submit("alpha", ["weak", "answer"])
        gate.entered.wait(5.0)
        pending = await instance.submit("beta", ["middle", "other"])
        gate.release.set()
        instance.shutdown(drain=False, timeout=5.0)
        await asyncio.wait_for(scores_of(held), 5.0)
        with pytest.raises(RerankSchedulerClosed):
            await asyncio.wait_for(scores_of(pending), 5.0)
        return instance

    instance = asyncio.run(main())

    assert instance.pending_requests() == 0
    assert not any(worker.is_alive() for worker in instance._workers)
    # Admission is closed for good: a later submitter is refused, not hung.
    with pytest.raises(RerankSchedulerOverloaded):
        asyncio.run(instance.submit("alpha", ["weak"]))


def test_shutdown_drains_accepted_work_and_terminates_workers():
    model = ScoringModel()
    instance = CrossEncoderReranker(config(), model_factory=lambda *_: model)

    async def main():
        return await instance.rerank("alpha", candidates("weak", "answer"))

    assert asyncio.run(main()).status == "success"
    assert instance.shutdown(timeout=5.0) is True
    assert not any(worker.is_alive() for worker in instance.scheduler._workers)


# ---------------------------------------------------------------------------
# 13. The regression gate against the pre-CONC-05 behavior
# ---------------------------------------------------------------------------


def legacy_rerank(model, query: str, bounded: List[dict], batch_size: int):
    """The pre-CONC-05 uncontended path, reproduced exactly.

    One `predict` over one request's pairs, then the same sort key. This is
    the reference the scheduler must reproduce bit for bit when nothing else
    is competing for the model.
    """
    passages = [item["text"] for item in bounded]
    values = model.predict(
        [(query, passage) for passage in passages],
        batch_size=batch_size,
        show_progress_bar=False,
    )
    scores = [float(value) for value in values]
    ranked = sorted(
        enumerate(bounded), key=lambda item: (-scores[item[0]], item[0])
    )
    return [item["chunk_id"] for _, item in ranked], scores


def test_uncontended_scores_and_ranking_match_the_previous_implementation():
    cands = candidates("weak", "answer", "middle", "dup", "other", "dup")
    expected_order, expected_scores = legacy_rerank(
        ScoringModel(), "alpha", cands, batch_size=4
    )

    async def main():
        with reranker(ScoringModel()) as instance:
            return await instance.rerank("alpha", cands)

    result = asyncio.run(main())

    assert result.status == "success"
    assert [item["chunk_id"] for item in result.candidates] == expected_order
    by_id = {item["chunk_id"]: item["reranker_score"] for item in result.candidates}
    for index, candidate in enumerate(cands):
        assert by_id[candidate["chunk_id"]] == pytest.approx(
            expected_scores[index], rel=1e-6, abs=1e-6
        )
