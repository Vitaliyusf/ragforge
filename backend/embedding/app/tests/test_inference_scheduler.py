"""CONC-04 focused regression: the bounded embedding inference scheduler.

These tests prove the properties the task owns — combination, bounds, result
ownership, fairness, failure fan-out and shutdown — without loading a real
model. The fake model records every physical forward pass, which is exactly
the evidence "fewer inference calls" needs.
"""
import threading
import time
from types import SimpleNamespace

import pytest

from app.embedding.interfaces import IEmbeddingModel
from app.services.embedding_handler import QueryEmbeddingHandler
from app.services.inference_scheduler import (
    CLASS_BACKGROUND,
    CLASS_LIVE,
    EmbeddingScheduler,
    EmbeddingSchedulerClosed,
    EmbeddingSchedulerOverloaded,
    EmbeddingSchedulerResultMismatch,
    create_scheduler,
)
from shared.bounded_executor import ExecutorOverloaded


class RecordingModel(IEmbeddingModel):
    """Deterministic model that records every physical batch it is given."""

    def __init__(self, *, delay=0.0, fail_times=0, short_result=False):
        self.batches = []
        self.delay = delay
        self.fail_times = fail_times
        self.short_result = short_result
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self._lock = threading.Lock()

    def encode(self, text):
        return self.encode_batch([text])[0]

    def encode_batch(self, texts, batch_size=32):
        with self._lock:
            self.batches.append(list(texts))
            failing = self.fail_times > 0
            if failing:
                self.fail_times -= 1
        self.entered.set()
        self.release.wait(5.0)
        if self.delay:
            time.sleep(self.delay)
        if failing:
            raise RuntimeError("model exploded")
        if self.short_result:
            return [[1.0]]
        # The vector encodes its own text so result ownership is checkable.
        return [[float(len(text)), float(hash(text) % 1000)] for text in texts]

    def is_loaded(self):
        return True

    @property
    def calls(self):
        return len(self.batches)


class RecordingLogger:
    def __init__(self):
        self.entries = []

    def log(self, location, message, data=None, hypothesis_id="A"):
        self.entries.append((location, message, data or {}))


def make_config(**overrides):
    base = {
        "service_name": "embedding",
        "model_name": "intfloat/multilingual-e5-small",
        "embedding_query_prefix": "query: ",
        "embedding_passage_prefix": "passage: ",
        "embedding_max_batch_size": 8,
        "embedding_microbatch_window_ms": 25.0,
        "embedding_max_pending_items": 64,
        "embedding_admission_timeout_seconds": 1.0,
        "embedding_inference_timeout_seconds": 10.0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def scheduler_factory():
    """Build started schedulers and guarantee their worker threads stop."""

    built = []

    def factory(model, **overrides):
        scheduler = create_scheduler(model, make_config(**overrides)).start()
        built.append(scheduler)
        return scheduler

    yield factory
    for scheduler in built:
        scheduler.shutdown()


def submit_concurrently(scheduler, texts, scheduling_class=CLASS_LIVE):
    """Run one blocking submission per thread and collect ordered outcomes."""

    results = [None] * len(texts)
    errors = [None] * len(texts)
    ready = threading.Barrier(len(texts))

    def run(index):
        ready.wait(5.0)
        try:
            results[index] = scheduler.encode_one(
                texts[index], scheduling_class=scheduling_class
            )
        except BaseException as exc:  # recorded, then asserted on
            errors[index] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(texts))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10.0)
    return results, errors


# ── 1. concurrent callers combine into fewer physical inference calls ────────


def test_concurrent_callers_share_one_physical_inference_call(scheduler_factory):
    # The collection window is only paid while the scheduler is busy, so the
    # model has to take real time for there to be anything to combine into.
    model = RecordingModel(delay=0.02)
    scheduler = scheduler_factory(model, embedding_microbatch_window_ms=25.0)

    texts = [f"query: q{i}" for i in range(12)]
    results, errors = submit_concurrently(scheduler, texts)

    assert errors == [None] * 12
    assert all(result is not None for result in results)
    # Twelve independent callers, far fewer than twelve forward passes.
    assert model.calls < 12
    assert max(len(batch) for batch in model.batches) > 1
    assert sum(len(batch) for batch in model.batches) == 12


def test_an_idle_scheduler_does_not_pay_the_collection_window(scheduler_factory):
    """A lone query on an idle scheduler is dispatched without waiting."""

    model = RecordingModel()
    scheduler = scheduler_factory(model, embedding_microbatch_window_ms=500.0)

    started = time.monotonic()
    assert scheduler.encode_one("query: alone")
    assert time.monotonic() - started < 0.25


# ── 2. max batch size is never exceeded ──────────────────────────────────────


def test_physical_batches_never_exceed_the_configured_maximum(scheduler_factory):
    model = RecordingModel()
    scheduler = scheduler_factory(model, embedding_max_batch_size=4)

    _, errors = submit_concurrently(scheduler, [f"query: q{i}" for i in range(20)])

    assert errors == [None] * 20
    assert model.batches, "no inference happened"
    assert max(len(batch) for batch in model.batches) <= 4
    assert sum(len(batch) for batch in model.batches) == 20


# ── 3. the pending queue is bounded, with a typed overload ───────────────────


def test_pending_queue_is_bounded_and_refuses_typed_overload(scheduler_factory):
    model = RecordingModel()
    scheduler = scheduler_factory(
        model,
        embedding_max_batch_size=2,
        embedding_max_pending_items=4,
        embedding_admission_timeout_seconds=0.05,
    )
    model.release.clear()  # hold the first forward pass open

    accepted = []
    rejected = []

    def run(index):
        try:
            scheduler.encode_one(f"query: hold{index}")
            accepted.append(index)
        except EmbeddingSchedulerOverloaded:
            rejected.append(index)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(24)]
    for thread in threads:
        thread.start()
    assert model.entered.wait(5.0)
    time.sleep(0.3)

    assert scheduler.pending_items() <= 4
    model.release.set()
    for thread in threads:
        thread.join(10.0)

    assert rejected, "a bounded queue must shed work under a flood"
    assert len(accepted) + len(rejected) == 24


def test_scheduler_overload_is_the_transport_recognised_overload_type():
    """The RPC boundary translates ExecutorOverloaded into a busy reply."""

    assert issubclass(EmbeddingSchedulerOverloaded, ExecutorOverloaded)


# ── 4/5. result ownership, including duplicate texts ─────────────────────────


def test_every_item_receives_its_own_vector_across_a_mixed_batch(scheduler_factory):
    model = RecordingModel()
    scheduler = scheduler_factory(model)

    texts = ["query: a", "query: bb", "query: ccc", "query: dddd"]
    results, errors = submit_concurrently(scheduler, texts)

    assert errors == [None] * 4
    # The fake vector's first component is the input length, so a shuffled
    # fan-out would be visible here.
    assert [result[0] for result in results] == [float(len(text)) for text in texts]


def test_duplicate_texts_stay_distinct_submissions(scheduler_factory):
    model = RecordingModel()
    scheduler = scheduler_factory(model)

    results = scheduler.encode(
        ["passage: same", "passage: same", "passage: other"],
        scheduling_class=CLASS_BACKGROUND,
    )

    assert len(results) == 3
    assert results[0] == results[1]
    submitted = [text for batch in model.batches for text in batch]
    # Nothing is deduplicated: three logical items reach the model.
    assert submitted.count("passage: same") == 2


# ── 6. cancellation does not corrupt neighbouring items ──────────────────────


def test_a_timed_out_caller_does_not_shift_neighbouring_results(scheduler_factory):
    model = RecordingModel()
    # One worker, so a single held forward pass keeps everything below pending.
    # The property under test — a cancelled item is dropped before composition
    # rather than shifting its neighbours — does not depend on worker count.
    scheduler = scheduler_factory(
        model, embedding_microbatch_window_ms=200.0, embedding_inference_workers=1
    )
    model.release.clear()

    # Occupy the worker so everything below is still pending when the
    # abandoned caller gives up.
    warmup = threading.Thread(target=scheduler.encode_one, args=("query: warmup",))
    warmup.start()
    assert model.entered.wait(5.0)

    survivors = {}

    def survivor(name):
        survivors[name] = scheduler.encode_one(f"query: {name}")

    threads = [threading.Thread(target=survivor, args=(name,)) for name in ("aa", "bbbb")]
    abandoned_error = []

    def abandon():
        try:
            scheduler.encode_one("query: abandoned", timeout=0.2)
        except BaseException as exc:
            abandoned_error.append(exc)

    threads.append(threading.Thread(target=abandon))
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + 5.0
    while scheduler.pending_items() < 3 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert scheduler.pending_items() == 3

    threads[-1].join(5.0)
    assert abandoned_error and isinstance(abandoned_error[0], TimeoutError)

    model.release.set()
    for thread in threads:
        thread.join(10.0)
    warmup.join(10.0)

    # The abandoned item was dropped before composition, so neither survivor's
    # result index moved onto its neighbour's vector.
    assert survivors["aa"][0] == float(len("query: aa"))
    assert survivors["bbbb"][0] == float(len("query: bbbb"))
    assert "query: abandoned" not in [text for batch in model.batches for text in batch]


# ── 7. a failed batch completes every affected waiter ────────────────────────


def test_a_failed_forward_pass_completes_all_affected_waiters(scheduler_factory):
    model = RecordingModel(fail_times=1)
    scheduler = scheduler_factory(model)

    _, errors = submit_concurrently(scheduler, [f"query: q{i}" for i in range(4)])

    # No waiter is left hanging: each one either got a vector from a later
    # batch or the batch's own exception.
    assert all(error is None or isinstance(error, RuntimeError) for error in errors)
    assert any(isinstance(error, RuntimeError) for error in errors)


def test_a_vector_count_mismatch_is_reported_as_a_typed_contract_failure(scheduler_factory):
    model = RecordingModel(short_result=True)
    scheduler = scheduler_factory(model)

    with pytest.raises(EmbeddingSchedulerResultMismatch):
        scheduler.encode(["passage: a", "passage: b"], scheduling_class=CLASS_BACKGROUND)


# ── 8. live traffic progresses under sustained background load ───────────────


def test_live_work_progresses_while_background_saturates_the_queue(scheduler_factory):
    model = RecordingModel(delay=0.01)
    scheduler = scheduler_factory(
        model,
        embedding_max_batch_size=8,
        embedding_max_pending_items=64,
        embedding_inference_timeout_seconds=20.0,
    )

    stop = threading.Event()
    background_done = []

    def flood():
        while not stop.is_set():
            try:
                scheduler.encode(
                    [f"passage: bg{i}" for i in range(8)],
                    scheduling_class=CLASS_BACKGROUND,
                )
                background_done.append(1)
            except Exception:
                pass

    floods = [threading.Thread(target=flood) for _ in range(4)]
    for thread in floods:
        thread.start()
    time.sleep(0.2)

    live_latencies = []
    try:
        for index in range(10):
            started = time.monotonic()
            assert scheduler.encode_one(f"query: live{index}")
            live_latencies.append(time.monotonic() - started)
    finally:
        stop.set()
        for thread in floods:
            thread.join(10.0)

    assert len(live_latencies) == 10
    assert background_done, "background work must also make progress"
    # Live latency stays bounded: it is never made to wait behind the whole
    # background backlog.
    assert max(live_latencies) < 2.0


# ── 9. shutdown drains or fails pending work deterministically ───────────────


def test_shutdown_drains_accepted_work(scheduler_factory):
    model = RecordingModel()
    scheduler = create_scheduler(model, make_config()).start()

    results = scheduler.encode(["passage: x"], scheduling_class=CLASS_BACKGROUND)
    assert scheduler.shutdown() is True
    assert scheduler.pending_items() == 0
    assert len(results) == 1


def test_shutdown_without_drain_fails_pending_waiters_explicitly():
    model = RecordingModel()
    scheduler = EmbeddingScheduler(
        model,
        service="embedding",
        max_batch_size=1,
        microbatch_window_ms=5.0,
        max_pending_items=16,
        admission_timeout_seconds=1.0,
        inference_timeout_seconds=10.0,
        inference_workers=1,
    ).start()
    model.release.clear()

    # Occupy the worker, so everything submitted afterwards is provably queued.
    holder = threading.Thread(target=scheduler.encode_one, args=("query: holder",))
    holder.start()
    assert model.entered.wait(5.0)

    errors = []

    def run(index):
        try:
            scheduler.encode_one(f"query: pending{index}")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(3)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 5.0
    while scheduler.pending_items() < 3 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert scheduler.pending_items() == 3

    scheduler.shutdown(drain=False, timeout=2.0)
    model.release.set()
    for thread in threads:
        thread.join(10.0)
    holder.join(10.0)

    assert scheduler.pending_items() == 0
    # Queued work is failed explicitly, never abandoned to a hanging future.
    assert len(errors) == 3
    assert all(isinstance(exc, EmbeddingSchedulerClosed) for exc in errors)


def test_submission_after_shutdown_is_refused_not_queued():
    model = RecordingModel()
    scheduler = create_scheduler(model, make_config()).start()
    scheduler.shutdown()

    with pytest.raises(EmbeddingSchedulerOverloaded) as error:
        scheduler.encode_one("query: too late")
    assert error.value.reason == "closed"


# ── 10. every migrated path uses the same scheduler and model ────────────────


def test_query_handler_embeds_through_the_shared_scheduler(scheduler_factory):
    model = RecordingModel()
    scheduler = scheduler_factory(model)
    handler = QueryEmbeddingHandler(scheduler, RecordingLogger(), make_config())

    reply = handler.process_request_with_reply(
        {"action": "embed", "correlation_id": "c-1", "payload": {"text": "hello"}},
        "rag.replies",
        "c-1",
    )

    assert reply["correlation_id"] == "c-1"
    assert reply["data"]["embedding"]
    # The E5 query prefix survives the migration untouched.
    assert model.batches == [["query: hello"]]
    assert handler.scheduler is scheduler
    assert not hasattr(handler, "embedding_model")


def test_query_and_ingestion_share_one_scheduler_and_one_model(scheduler_factory):
    """Live and background items reach the same model through one batch path."""

    model = RecordingModel(delay=0.02)
    scheduler = scheduler_factory(model, embedding_microbatch_window_ms=100.0)
    model.release.clear()

    outcomes = {}

    def live():
        outcomes["live"] = scheduler.encode_one("query: interactive")

    def ingest():
        outcomes["bg"] = scheduler.encode(
            ["passage: c0", "passage: c1"], scheduling_class=CLASS_BACKGROUND
        )

    threads = [threading.Thread(target=live), threading.Thread(target=ingest)]
    for thread in threads:
        thread.start()
    time.sleep(0.15)
    model.release.set()
    for thread in threads:
        thread.join(10.0)

    assert len(outcomes["bg"]) == 2
    assert outcomes["live"]
    submitted = [text for batch in model.batches for text in batch]
    assert sorted(submitted) == ["passage: c0", "passage: c1", "query: interactive"]


def test_scheduler_rejects_a_submission_larger_than_its_pending_bound(scheduler_factory):
    model = RecordingModel()
    scheduler = scheduler_factory(
        model, embedding_max_batch_size=2, embedding_max_pending_items=4
    )

    with pytest.raises(EmbeddingSchedulerOverloaded) as error:
        scheduler.encode(
            [f"passage: c{i}" for i in range(10)], scheduling_class=CLASS_BACKGROUND
        )
    assert error.value.reason == "oversized"
    assert model.calls == 0
