"""One machine-readable summary of everything a benchmark measured.

A benchmark document is a phase table: each phase carries the ``results``
its eval run produced, and each run carries the per-item rows those results
were averaged from. That is the right shape for the UI, which drills down,
and the wrong shape for anyone analysing a benchmark outside this service —
who needs the numbers, their denominators and their distribution in one flat
document that can be diffed against another benchmark's.

This module produces that document. It computes nothing new: every IR,
answer-quality and failure figure here is the one the run already stored,
copied under a stable key. The only figures it derives are the latency
percentiles, and those come from the per-item rows the runs already wrote —
never from a distribution assumed around a mean.

Three rules hold it together:

**Unmeasured is ``null``, and a denominator always travels with a mean.**
A phase that never ran has ``null`` metrics and ``null`` item counts, not
zeros: "Recall@5: 0%" for a phase nobody executed is a claim about the
system that nobody measured. Every mean is reported beside the counts it was
taken over, so a precision of 1.0 over two items cannot be read as the same
evidence as one over two hundred.

**Valid JSON only.** ``NaN`` and ``Infinity`` are not JSON, but they survive
a round trip through BSON and would reach an export as literals that break
strict parsers. Every number that leaves this module passes through
:func:`_number`, which turns a non-finite value into ``None`` — an unusable
number is unmeasured, and it says so.

**Where a figure came from is part of the figure.** A latency block states
its ``source``: ``per_item`` when the summary saw the individual samples and
could compute percentiles, ``phase_aggregate`` when only the run's own mean
was available and the percentiles are therefore unknown. Reporting the mean
either way with no way to tell them apart would invite a reader to compare a
p95 that exists against one that silently does not.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from app.services.eval_runner import K_VALUES
from app.services.failure_attribution import FAILURE_CATEGORIES

# Bumped when the summary's *shape* changes, for the reason the manifest
# carries a version: a summary read back later must be interpretable under
# the rules it was written with.
SUMMARY_VERSION = 1

# The IR metrics a retrieval phase reports at every k.
_AT_K_METRICS = ("recall_at_k", "precision_at_k", "hit_rate_at_k", "ndcg_at_k")

# Per-item counters every eval run writes. Their sum is how many items the
# phase actually reached.
_ITEM_COUNTERS = ("evaluated", "skipped", "unscorable", "failed")

# Answer-quality fields that arrive as ``{"mean", "counted", "excluded"}``
# from `citation_metrics.aggregate_mean`, and the ones that are a bare rate.
_QUALITY_MEAN_FIELDS = (
    "groundedness",
    "citation_precision",
    "citation_recall",
    "unsupported_claims",
)
_QUALITY_RATE_FIELDS = ("hallucination_rate", "hallucination_severe_rate")

# Percentiles reported for every latency distribution, as (key, quantile).
_PERCENTILES = (("p50", 0.50), ("p95", 0.95), ("p99", 0.99))

# What a latency block's numbers were derived from.
SOURCE_PER_ITEM = "per_item"
SOURCE_PHASE_AGGREGATE = "phase_aggregate"


def _number(value: Any) -> Optional[float]:
    """One stored number as a JSON-safe float, or ``None``.

    A bool is rejected before the numeric check: ``True`` is an ``int`` in
    Python, and a metric of ``1.0`` sourced from a flag is a fabrication.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _count(value: Any) -> Optional[int]:
    """One stored counter as an int, or ``None`` when it is not a count."""
    number = _number(value)
    return None if number is None else int(number)


def _percentile(ordered: Sequence[float], quantile: float) -> float:
    """Nearest-rank percentile of an already sorted, non-empty sample.

    Nearest rank rather than interpolation: every value reported is a
    latency that was actually observed, and a single-sample phase yields
    that sample at every percentile instead of an interpolation artefact.
    """
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def latency_distribution(
    samples: Iterable[Any],
    *,
    fallback_mean_ms: Any = None,
) -> Dict[str, Any]:
    """Summarize per-item latencies, or fall back to a recorded mean.

    Args:
        samples: Per-item ``latency_ms`` values, of which the non-numeric and
            non-finite ones are discarded rather than counted.
        fallback_mean_ms: The phase's own ``mean_latency_ms``, used only when
            no samples were available. Its percentiles stay ``None``: a mean
            says nothing about a tail, and inventing one would be the whole
            reason this module exists, backwards.

    Returns:
        A block whose ``sample_count`` is always the number of usable samples
        seen — so one sourced from ``phase_aggregate`` reports ``0``, because
        it saw none.
    """
    ordered = sorted(
        number for number in (_number(value) for value in samples) if number is not None
    )
    block: Dict[str, Any] = {
        "source": None,
        "sample_count": len(ordered),
        "mean": None,
        "min": None,
        "max": None,
        **{key: None for key, _ in _PERCENTILES},
    }
    if ordered:
        block["source"] = SOURCE_PER_ITEM
        block["mean"] = sum(ordered) / len(ordered)
        block["min"] = ordered[0]
        block["max"] = ordered[-1]
        for key, quantile in _PERCENTILES:
            block[key] = _percentile(ordered, quantile)
        return block

    recorded = _number(fallback_mean_ms)
    if recorded is not None:
        block["source"] = SOURCE_PHASE_AGGREGATE
        block["mean"] = recorded
    return block


def _at_k(stored: Any) -> Dict[str, Optional[float]]:
    """One at-k metric over the full :data:`K_VALUES` grid.

    Always every k, whatever the stored dict holds: two benchmarks are
    compared key by key, and a k missing from one document because that run
    predates it must read as unmeasured rather than shift the alignment.
    """
    values = stored if isinstance(stored, Mapping) else {}
    return {str(k): _number(values.get(str(k))) for k in K_VALUES}


def _retrieval_block(results: Mapping[str, Any]) -> Dict[str, Any]:
    """The IR metrics a phase reported, at every k, plus MRR."""
    block: Dict[str, Any] = {
        metric: _at_k(results.get(metric)) for metric in _AT_K_METRICS
    }
    block["mrr"] = _number(results.get("mrr"))
    return block


def _items_block(results: Mapping[str, Any]) -> Dict[str, Any]:
    """The phase's denominators, with the total it reached.

    ``reached`` is the sum of the four counters and not the dataset size: an
    item the phase never got to is not evidence of anything, and putting the
    dataset size here would make every rate look better than it is.
    """
    counts = {
        name: _count(results.get(f"items_{name}")) or 0 for name in _ITEM_COUNTERS
    }
    return {**counts, "reached": sum(counts.values())}


def _quality_block(stored: Any) -> Optional[Dict[str, Any]]:
    """Answer-quality figures, each still carrying its own denominator."""
    if not isinstance(stored, Mapping):
        return None
    block: Dict[str, Any] = {}
    for field in _QUALITY_MEAN_FIELDS:
        value = stored.get(field)
        measured = value if isinstance(value, Mapping) else {}
        block[field] = {
            "mean": _number(measured.get("mean")),
            "counted": _count(measured.get("counted")) or 0,
            "excluded": _count(measured.get("excluded")) or 0,
        }
    for field in _QUALITY_RATE_FIELDS:
        block[field] = _number(stored.get(field))
    block["items_judged"] = _count(stored.get("items_judged")) or 0
    block["items_unjudged"] = _count(stored.get("items_unjudged")) or 0
    return block


def _attribution_from_counts(
    counts: Mapping[str, int],
    attributed: int,
) -> Dict[str, Any]:
    """Build an attribution block, recomputing rates from the counts.

    Rates are recomputed rather than copied so a pooled block and a
    per-phase one are produced by the same arithmetic, and so a stored rate
    can never survive a summing that invalidated it. Every rate is ``None``
    when nothing was attributable: ``0%`` would claim a clean run nobody
    measured.
    """
    return {
        "counts": dict(counts),
        "rates": {
            category: (counts[category] / attributed) if attributed else None
            for category in FAILURE_CATEGORIES
        },
        "items_attributed": attributed,
    }


def _attribution_block(stored: Any) -> Optional[Dict[str, Any]]:
    """Stage-failure counts over the full category list, with rates."""
    if not isinstance(stored, Mapping):
        return None
    stored_counts = stored.get("counts")
    counts_source = stored_counts if isinstance(stored_counts, Mapping) else {}
    counts = {
        category: _count(counts_source.get(category)) or 0
        for category in FAILURE_CATEGORIES
    }
    return _attribution_from_counts(
        counts, _count(stored.get("items_attributed")) or 0
    )


def _index_rows(runs: Optional[Iterable[Mapping[str, Any]]]) -> Dict[str, List[Any]]:
    """Map each supplied run's id to its per-item latency values.

    Runs are optional throughout: a caller holding only the benchmark
    document still gets a complete summary, with the latency blocks saying
    they came from a phase aggregate. Nothing else is read from a run here —
    its rows carry query text and retrieved content, and a summary is not
    the place for either.
    """
    rows: Dict[str, List[Any]] = {}
    for run in runs or ():
        if not isinstance(run, Mapping):
            continue
        run_id = run.get("run_id")
        if not run_id:
            continue
        per_item = run.get("per_item")
        rows[str(run_id)] = [
            row.get("latency_ms")
            for row in (per_item if isinstance(per_item, list) else ())
            if isinstance(row, Mapping)
        ]
    return rows


def _phase_latency_samples(
    phase: Mapping[str, Any],
    rows_by_run: Mapping[str, List[Any]],
) -> List[Any]:
    """The per-item latencies belonging to one phase's run, if we have them."""
    run_id = phase.get("run_id")
    if not run_id:
        return []
    return list(rows_by_run.get(str(run_id), ()))


def summarize_phase(
    phase: Mapping[str, Any],
    *,
    latency_samples: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Flatten one phase record into the summary's phase shape.

    A phase that produced no ``results`` — unsupported, skipped, still
    queued, or failed before it scored anything — keeps its identity and its
    reason, and every metric block is ``None``. That is the difference
    between "measured nothing" and "measured zero", and the phase's own
    ``status`` and ``reason`` say which of the two happened.
    """
    stored = phase.get("results")
    results: Mapping[str, Any] = stored if isinstance(stored, Mapping) else {}
    return {
        "name": phase.get("name"),
        "status": phase.get("status"),
        "evaluation_mode": phase.get("evaluation_mode"),
        "pipeline_mode": phase.get("pipeline_mode"),
        "run_id": phase.get("run_id"),
        "reason": phase.get("reason"),
        "error": phase.get("error"),
        "started_at": phase.get("started_at"),
        "finished_at": phase.get("finished_at"),
        "items": _items_block(results) if results else None,
        "retrieval": _retrieval_block(results) if results else None,
        "answer_quality": _quality_block(results.get("answer_quality")),
        "failure_attribution": _attribution_block(results.get("failure_attribution")),
        "latency_ms": latency_distribution(
            latency_samples or (),
            fallback_mean_ms=results.get("mean_latency_ms"),
        ),
    }


def _totals(
    phases: List[Dict[str, Any]],
    pooled_latency: List[Any],
) -> Dict[str, Any]:
    """Roll the phase table up into the figures that survive a rollup.

    Item counts, failure counts and latency samples are summable: each phase
    contributes independent observations of the same corpus. IR and
    answer-quality means are deliberately absent — averaging a retrieval
    phase's Recall@5 with an end-to-end phase's would produce a number
    describing no measurement anyone performed.
    """
    measured = [phase for phase in phases if phase["items"] is not None]
    items = {
        name: sum(phase["items"][name] for phase in measured)
        for name in (*_ITEM_COUNTERS, "reached")
    }
    counts = {category: 0 for category in FAILURE_CATEGORIES}
    attributed = 0
    for phase in phases:
        block = phase["failure_attribution"]
        if block is None:
            continue
        attributed += block["items_attributed"]
        for category in FAILURE_CATEGORIES:
            counts[category] += block["counts"][category]
    statuses: Dict[str, int] = {}
    for phase in phases:
        status = phase["status"]
        if status is not None:
            statuses[str(status)] = statuses.get(str(status), 0) + 1
    return {
        "total_phases": len(phases),
        "measured_phases": len(measured),
        "phase_status_counts": statuses,
        "items": items if measured else None,
        "failure_attribution": _attribution_from_counts(counts, attributed),
        # Pooled from the per-item samples only. A mean of phase means would
        # weight a phase that reached two items like one that reached two
        # hundred, and there is no honest pooled percentile at all without
        # the samples themselves.
        "latency_ms": latency_distribution(pooled_latency),
    }


def summarize_benchmark(
    benchmark: Mapping[str, Any],
    *,
    runs: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Summarize one benchmark and its runs into a single JSON-safe document.

    Args:
        benchmark: The stored benchmark document, as
            :meth:`EvalStore.get_benchmark_run` returns it. A partial one —
            still running, or missing its phase table entirely — summarizes
            to the same shape, with the unmeasured values as ``None``.
        runs: The eval runs the phases became, in any order, each as
            :meth:`EvalStore.get_run` returns it. Read only for their
            per-item latencies, and matched to phases by ``run_id``, so a run
            belonging to another benchmark contributes nothing. Omit them and
            every latency block falls back to the phase's own mean.

    Returns:
        A document whose every number is finite or ``None``, safe to
        ``json.dumps`` without ``allow_nan``.
    """
    stored_phases = benchmark.get("phases")
    rows_by_run = _index_rows(runs)
    phases: List[Dict[str, Any]] = []
    pooled: List[Any] = []
    for phase in stored_phases if isinstance(stored_phases, list) else ():
        if not isinstance(phase, Mapping):
            continue
        samples = _phase_latency_samples(phase, rows_by_run)
        pooled.extend(samples)
        phases.append(summarize_phase(phase, latency_samples=samples))

    return {
        "summary_version": SUMMARY_VERSION,
        "benchmark_id": benchmark.get("benchmark_id"),
        "dataset_id": benchmark.get("dataset_id"),
        "dataset_version": benchmark.get("dataset_version"),
        "dataset_sha256": benchmark.get("dataset_sha256"),
        "status": benchmark.get("status"),
        "created_at": benchmark.get("created_at"),
        "started_at": benchmark.get("started_at"),
        "finished_at": benchmark.get("finished_at"),
        "error": benchmark.get("error"),
        "phases": phases,
        "totals": _totals(phases, pooled),
    }
