"""Small, fixed-shape CONC-05 probe for the learned-reranker scheduler.

Deterministic and offline. It drives the *real*
:class:`~app.services.learned_reranker.CrossEncoderReranker` and its real
scheduler, but behind a stub model whose forward pass costs a fixed per-call
overhead plus a fixed per-pair cost.

That is the honest scope of this probe, and it must be reported as such: it
measures the **scheduler** — admission, queueing, batch composition, fairness
and the learned-rerank success rate under concurrency — not the throughput of
`BAAI/bge-reranker-v2-m3`. The pinned model is baked into the RAG image and
`sentence_transformers`/`torch` are not installed in the host validation
interpreter, so a real-model number cannot be produced here. Checkpoint B owns
that measurement.

The stub's two costs are the assumption everything else rests on:

* ``--call-overhead-ms`` — tokenizer setup, padding, dispatch: paid once per
  physical ``predict`` call regardless of size. This is what micro-batching
  amortises, and if it were zero batching could only ever add latency.
* ``--pair-cost-ms`` — per-pair compute, paid for every pair either way.

Usage::

    py -3.12 scripts/perf/reranker_concurrency_probe.py
    py -3.12 scripts/perf/reranker_concurrency_probe.py --json artifact.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / "backend", ROOT / "backend" / "rag"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.learned_reranker import CrossEncoderReranker  # noqa: E402
from shared.metrics import METRICS  # noqa: E402

#: The production candidate depth (`RERANKER_CANDIDATE_K`), so a request in
#: this probe is the shape a real retrieval turn produces.
CANDIDATES = 20
CONCURRENCY_LEVELS = (1, 2, 4, 8)
REQUESTS_PER_CLIENT = 12


class StubCrossEncoder:
    """A cross-encoder-shaped cost model with a recorded call history."""

    def __init__(self, call_overhead_ms: float, pair_cost_ms: float) -> None:
        self.call_overhead = call_overhead_ms / 1000.0
        self.pair_cost = pair_cost_ms / 1000.0
        self.batch_sizes: List[int] = []
        self._lock = threading.Lock()

    def predict(self, pairs, **_kwargs):
        pairs = list(pairs)
        with self._lock:
            self.batch_sizes.append(len(pairs))
        time.sleep(self.call_overhead + self.pair_cost * len(pairs))
        # Derived from the pair's content alone — never from its position in
        # the physical batch. A real cross-encoder scores each pair
        # independently, and a stub whose score moved with batch composition
        # would manufacture exactly the quality drift this probe checks for.
        return [_stub_score(query, passage) for query, passage in pairs]

    def reset(self) -> None:
        with self._lock:
            self.batch_sizes = []


def _stub_score(query: str, passage: str) -> float:
    return float(len(passage)) + (sum(ord(char) for char in query + passage) % 97) / 10.0


def candidates() -> List[Dict[str, Any]]:
    return [
        {
            "chunk_id": f"c{index}",
            "text": f"candidate passage number {index} " + "x" * (index % 11),
            "score": 1.0 - index * 0.01,
        }
        for index in range(CANDIDATES)
    ]


def config(**overrides: Any) -> Any:
    from types import SimpleNamespace

    values = {
        "service_name": "rag",
        "reranker_enabled": True,
        "reranker_model": "stub",
        "reranker_model_revision": "stub",
        "reranker_candidate_k": CANDIDATES,
        "reranker_timeout_seconds": 30.0,
        "reranker_batch_size": 8,
        "reranker_max_length": 512,
        "reranker_microbatch_window_ms": 0.0,
        "reranker_max_batch_pairs": 64,
        "reranker_max_pending_pairs": 512,
        "reranker_admission_timeout_seconds": 1.0,
        "reranker_inference_workers": 2,
        "reranker_max_background_inflight": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _queue_wait_totals() -> Dict[str, float]:
    """Read the queue-wait histogram's running sum/count from the registry."""
    totals = {"sum": 0.0, "count": 0.0}
    for metric in METRICS.reranker_scheduler_queue_wait_seconds.collect():
        for sample in metric.samples:
            if sample.name.endswith("_sum"):
                totals["sum"] += sample.value
            elif sample.name.endswith("_count"):
                totals["count"] += sample.value
    return totals


def percentile(values: Sequence[float], fraction: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


async def _client(
    reranker: CrossEncoderReranker,
    traffic_class: str,
    requests: int,
    latencies: List[float],
    statuses: List[str],
    orderings: List[List[str]],
) -> None:
    pool = candidates()
    for _ in range(requests):
        started = time.perf_counter()
        result = await reranker.rerank("fixed probe query", pool, traffic_class=traffic_class)
        latencies.append(time.perf_counter() - started)
        statuses.append(result.status)
        if result.status == "success":
            orderings.append([item["chunk_id"] for item in result.candidates])


async def _scenario(
    name: str,
    model: StubCrossEncoder,
    live_clients: int,
    background_clients: int,
    requests: int,
    max_batch_pairs: int = 64,
    window_ms: float = 0.0,
) -> Dict[str, Any]:
    model.reset()
    reranker = CrossEncoderReranker(
        config(
            reranker_max_batch_pairs=max_batch_pairs,
            reranker_microbatch_window_ms=window_ms,
        ),
        model_factory=lambda *_: model,
    )
    latencies: List[float] = []
    statuses: List[str] = []
    orderings: List[List[str]] = []
    background_statuses: List[str] = []
    background_latencies: List[float] = []

    before = _queue_wait_totals()
    calls_before = reranker.scheduler.inference_calls
    pairs_before = reranker.scheduler.pairs_scored

    started = time.perf_counter()
    try:
        await asyncio.gather(
            *(
                _client(reranker, "live", requests, latencies, statuses, orderings)
                for _ in range(live_clients)
            ),
            *(
                _client(
                    reranker,
                    "eval",
                    requests,
                    background_latencies,
                    background_statuses,
                    [],
                )
                for _ in range(background_clients)
            ),
        )
    finally:
        wall = time.perf_counter() - started
        reranker.shutdown(timeout=10.0)

    after = _queue_wait_totals()
    waits = after["count"] - before["count"]
    calls = reranker.scheduler.inference_calls - calls_before
    pairs = reranker.scheduler.pairs_scored - pairs_before
    total = len(statuses) + len(background_statuses)
    success = statuses.count("success") + background_statuses.count("success")
    busy = statuses.count("busy") + background_statuses.count("busy")
    timeout = statuses.count("timeout") + background_statuses.count("timeout")
    error = statuses.count("error") + background_statuses.count("error")

    return {
        "scenario": name,
        "live_clients": live_clients,
        "background_clients": background_clients,
        "requests": total,
        "wall_seconds": round(wall, 4),
        "live_p50_ms": _ms(percentile(latencies, 0.50)),
        "live_p95_ms": _ms(percentile(latencies, 0.95)),
        "background_p50_ms": _ms(percentile(background_latencies, 0.50)),
        "background_p95_ms": _ms(percentile(background_latencies, 0.95)),
        "mean_queue_wait_ms": _ms(
            (after["sum"] - before["sum"]) / waits if waits else None
        ),
        "avg_batch_pairs": round(statistics.fmean(model.batch_sizes), 2)
        if model.batch_sizes
        else None,
        "p95_batch_pairs": percentile(model.batch_sizes, 0.95),
        "physical_calls": calls,
        "pairs_per_second": round(pairs / wall, 1) if wall else None,
        "success": success,
        "busy": busy,
        "timeout": timeout,
        "error": error,
        "learned_rerank_rate": round(success / total, 4) if total else None,
        "fallback_rate": round((total - success) / total, 4) if total else None,
        # One ordering is enough to prove the ranking did not move: every
        # successful request in a scenario reranked the same fixed candidates.
        "distinct_orderings": len({tuple(order) for order in orderings}),
    }


def _ms(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value * 1000, 2)


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
    model = StubCrossEncoder(args.call_overhead_ms, args.pair_cost_ms)
    rows: List[Dict[str, Any]] = []
    for level in CONCURRENCY_LEVELS:
        rows.append(
            await _scenario(f"live x{level}", model, level, 0, REQUESTS_PER_CLIENT)
        )
    rows.append(
        await _scenario("mixed live x2 + eval x4", model, 2, 4, REQUESTS_PER_CLIENT)
    )
    # Section 5 of the task: micro-batching is only worth keeping if it is
    # measurably better than not doing it. A batch bound equal to one
    # request's candidate count means no two requests can ever share a
    # forward pass, which is the scheduler with batching switched off.
    for level in (4, 8):
        rows.append(
            await _scenario(
                f"live x{level} (no batching)",
                model,
                level,
                0,
                REQUESTS_PER_CLIENT,
                max_batch_pairs=CANDIDATES,
            )
        )
    # The third option, and the one this task rejected: pay a collection
    # window so more requests can join a batch.
    for level in (4, 8):
        rows.append(
            await _scenario(
                f"live x{level} (5ms window)",
                model,
                level,
                0,
                REQUESTS_PER_CLIENT,
                max_batch_pairs=64,
                window_ms=5.0,
            )
        )
    return {
        "probe": "reranker_concurrency",
        "model": "stub",
        "call_overhead_ms": args.call_overhead_ms,
        "pair_cost_ms": args.pair_cost_ms,
        "candidates_per_request": CANDIDATES,
        "requests_per_client": REQUESTS_PER_CLIENT,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-overhead-ms", type=float, default=8.0)
    parser.add_argument("--pair-cost-ms", type=float, default=1.5)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    artifact = asyncio.run(_run(args))

    header = (
        f"{'scenario':<26}{'p50':>8}{'p95':>9}{'qwait':>8}{'avgB':>7}{'p95B':>6}"
        f"{'calls':>7}{'pairs/s':>9}{'ok':>5}{'busy':>6}{'t/o':>5}{'err':>5}{'fallb':>7}"
    )
    print(header)
    print("-" * len(header))
    for row in artifact["rows"]:
        print(
            f"{row['scenario']:<26}"
            f"{row['live_p50_ms'] or 0:>8.1f}"
            f"{row['live_p95_ms'] or 0:>9.1f}"
            f"{row['mean_queue_wait_ms'] or 0:>8.2f}"
            f"{row['avg_batch_pairs'] or 0:>7.1f}"
            f"{row['p95_batch_pairs'] or 0:>6.0f}"
            f"{row['physical_calls']:>7}"
            f"{row['pairs_per_second'] or 0:>9.1f}"
            f"{row['success']:>5}"
            f"{row['busy']:>6}"
            f"{row['timeout']:>5}"
            f"{row['error']:>5}"
            f"{row['fallback_rate']:>7.2f}"
        )
        if row["distinct_orderings"] > 1:
            print(f"  !! {row['scenario']}: concurrency changed the ordering")

    if args.json:
        args.json.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        print(f"\nartifact: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
