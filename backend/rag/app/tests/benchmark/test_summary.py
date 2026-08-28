"""Tests for the one machine-readable summary of a benchmark.

The metric blocks are built from :func:`app.services.eval_runner.aggregate`
output rather than from hand-written result dicts wherever a key's spelling
matters: a summary that read ``items_evaluated`` from a shape the runner
never writes would pass against a fixture and report ``null`` for every
finished phase in production.

The rest is the boundary behaviour the export depends on — an empty
benchmark, a phase that never ran, a stage that was never measured, a single
latency sample, and stored numbers that are not JSON at all — each asserted
to produce ``null`` rather than a zero, and every document asserted to
serialize under ``allow_nan=False``.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

import pytest

from app.services.benchmark_runner import (
    PHASE_COMPLETED,
    PHASE_END_TO_END_REGULAR,
    PHASE_QUEUED,
    PHASE_RETRIEVAL_BASE,
    PHASE_RETRIEVAL_EXTENDED,
    PHASE_UNSUPPORTED,
)
from app.services.benchmark_summary import (
    SOURCE_PER_ITEM,
    SOURCE_PHASE_AGGREGATE,
    SUMMARY_VERSION,
    latency_distribution,
    summarize_benchmark,
    summarize_phase,
)
from app.services.eval_runner import MODE_END_TO_END, MODE_RETRIEVAL, K_VALUES, aggregate
from app.services.failure_attribution import CATEGORY_RETRIEVAL, FAILURE_CATEGORIES


def scored_row(
    *,
    value: float = 1.0,
    latency_ms: Optional[float] = 10.0,
    **extra: Any,
) -> Dict[str, Any]:
    """One scored eval row, in the shape the runner stores."""
    return {
        "reciprocal_rank": value,
        "latency_ms": latency_ms,
        "scores": {
            metric: {str(k): value for k in K_VALUES}
            for metric in ("recall_at_k", "precision_at_k", "hit_rate_at_k", "ndcg_at_k")
        },
        **extra,
    }


def phase(
    name: str = PHASE_RETRIEVAL_BASE,
    *,
    status: str = PHASE_COMPLETED,
    run_id: Optional[str] = "run-1",
    results: Optional[Dict[str, Any]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """One phase record, as the benchmark document holds it."""
    return {
        "name": name,
        "status": status,
        "evaluation_mode": MODE_RETRIEVAL,
        "pipeline_mode": None,
        "run_id": run_id,
        "reason": None,
        "error": None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:01:00+00:00",
        "results": results,
        **extra,
    }


def benchmark(phases: List[Dict[str, Any]], **extra: Any) -> Dict[str, Any]:
    """One benchmark document carrying ``phases``."""
    return {
        "benchmark_id": "bm-1",
        "dataset_id": "ds-1",
        "dataset_version": 3,
        "dataset_sha256": "abc",
        "status": "completed",
        "phases": phases,
        **extra,
    }


def run(run_id: str, latencies: List[Any]) -> Dict[str, Any]:
    """One eval run document carrying only the rows the summary reads."""
    return {
        "run_id": run_id,
        "per_item": [{"latency_ms": value} for value in latencies],
    }


def as_json(document: Dict[str, Any]) -> str:
    """Serialize strictly, so NaN or Infinity anywhere fails the test."""
    return json.dumps(document, allow_nan=False)


# ── Metric passthrough ────────────────────────────────────────────────────

def test_a_finished_phase_reports_the_runner_s_own_metrics():
    """Every figure is the one the run stored, under a stable key."""
    results = aggregate([scored_row(value=1.0), {"skipped": True}], MODE_RETRIEVAL)

    summary = summarize_benchmark(benchmark([phase(results=results)]))
    measured = summary["phases"][0]

    assert summary["summary_version"] == SUMMARY_VERSION
    assert summary["benchmark_id"] == "bm-1"
    assert measured["retrieval"]["recall_at_k"]["5"] == pytest.approx(1.0)
    assert measured["retrieval"]["mrr"] == pytest.approx(1.0)
    assert measured["items"] == {
        "evaluated": 1,
        "skipped": 1,
        "unscorable": 0,
        "guardrail_blocked": 0,
        "failed": 0,
        "reached": 2,
    }


@pytest.mark.compat
def test_historical_results_without_guardrail_counter_remain_readable():
    summary = summarize_phase(phase(results={"items_evaluated": 1, "items_failed": 0}))

    assert summary["items"]["guardrail_blocked"] == 0


def test_every_k_is_present_even_when_the_stored_results_lack_it():
    """A run that predates a k must read as unmeasured, not shift alignment."""
    summary = summarize_phase(phase(results={"recall_at_k": {"5": 0.5}}))

    assert set(summary["retrieval"]["recall_at_k"]) == {str(k) for k in K_VALUES}
    assert summary["retrieval"]["recall_at_k"]["5"] == pytest.approx(0.5)
    assert summary["retrieval"]["recall_at_k"]["10"] is None
    assert summary["retrieval"]["mrr"] is None


def test_answer_quality_carries_its_own_denominators():
    """A mean over two judged answers is not the same claim as over two hundred."""
    rows = [
        {"hallucination_verdict": "severe", "groundedness": 0.2, "latency_ms": 5.0},
        {"hallucination_verdict": None, "groundedness": None, "latency_ms": 5.0},
    ]
    results = aggregate(rows, MODE_END_TO_END)

    quality = summarize_phase(
        phase(PHASE_END_TO_END_REGULAR, results=results)
    )["answer_quality"]

    assert quality["groundedness"]["mean"] == pytest.approx(0.2)
    assert quality["groundedness"]["counted"] == 1
    assert quality["groundedness"]["excluded"] == 1
    assert quality["hallucination_rate"] == pytest.approx(1.0)
    assert quality["items_judged"] == 1
    assert quality["items_unjudged"] == 1


def test_a_retrieval_phase_reports_no_answer_quality_stage():
    """A stage that was never measured is null, not an empty set of zeros."""
    results = aggregate([scored_row()], MODE_RETRIEVAL)

    assert summarize_phase(phase(results=results))["answer_quality"] is None


# ── Latency distribution ──────────────────────────────────────────────────

def test_percentiles_come_from_the_per_item_rows():
    """The tail is measured from the samples, never assumed around a mean."""
    latencies = [float(value) for value in range(1, 101)]

    summary = summarize_benchmark(
        benchmark([phase(results=aggregate([scored_row()]))]),
        runs=[run("run-1", latencies)],
    )
    block = summary["phases"][0]["latency_ms"]

    assert block["source"] == SOURCE_PER_ITEM
    assert block["sample_count"] == 100
    assert block["min"] == pytest.approx(1.0)
    assert block["max"] == pytest.approx(100.0)
    assert block["mean"] == pytest.approx(50.5)
    assert block["p50"] == pytest.approx(50.0)
    assert block["p95"] == pytest.approx(95.0)
    assert block["p99"] == pytest.approx(99.0)


def test_without_runs_the_mean_falls_back_and_the_tail_stays_unknown():
    """A recorded mean says nothing about a p95, so the p95 says nothing."""
    results = aggregate([scored_row(latency_ms=40.0), scored_row(latency_ms=60.0)])

    block = summarize_phase(phase(results=results))["latency_ms"]

    assert block["source"] == SOURCE_PHASE_AGGREGATE
    assert block["sample_count"] == 0
    assert block["mean"] == pytest.approx(50.0)
    assert block["p50"] is None and block["p95"] is None and block["p99"] is None
    assert block["min"] is None and block["max"] is None


def test_one_sample_is_reported_at_every_percentile():
    """Low sample counts must degrade to the observed value, not to NaN."""
    block = latency_distribution([12.5])

    assert block["sample_count"] == 1
    assert block["mean"] == pytest.approx(12.5)
    assert block["p50"] == pytest.approx(12.5)
    assert block["p95"] == pytest.approx(12.5)
    assert block["p99"] == pytest.approx(12.5)


def test_no_samples_and_no_recorded_mean_is_entirely_unknown():
    """Zero measurements is unknown latency, not zero latency."""
    block = latency_distribution([])

    assert block == {
        "source": None,
        "sample_count": 0,
        "mean": None,
        "min": None,
        "max": None,
        "p50": None,
        "p95": None,
        "p99": None,
    }


def test_a_run_from_another_benchmark_contributes_no_latency():
    """Phases take their samples by run_id, never by position."""
    summary = summarize_benchmark(
        benchmark([phase(results=aggregate([scored_row(latency_ms=None)]))]),
        runs=[run("run-other", [1.0, 2.0, 3.0])],
    )

    assert summary["phases"][0]["latency_ms"]["sample_count"] == 0
    assert summary["totals"]["latency_ms"]["sample_count"] == 0


def test_unusable_latency_samples_are_discarded_not_counted():
    """A row with no latency is not a zero-millisecond request."""
    block = latency_distribution([10.0, None, "slow", float("nan"), 30.0])

    assert block["sample_count"] == 2
    assert block["mean"] == pytest.approx(20.0)
    assert block["max"] == pytest.approx(30.0)


# ── Empty, partial and never-run phases ───────────────────────────────────

def test_an_empty_benchmark_summarizes_to_the_same_shape():
    """A document with nothing in it must still parse as a summary."""
    summary = summarize_benchmark({})

    assert summary["phases"] == []
    assert summary["benchmark_id"] is None
    assert summary["totals"]["items"] is None
    assert summary["totals"]["measured_phases"] == 0
    assert summary["totals"]["latency_ms"]["mean"] is None
    assert summary["totals"]["failure_attribution"]["rates"][CATEGORY_RETRIEVAL] is None
    assert as_json(summary)


def test_a_phase_that_never_ran_reports_null_not_zero():
    """An unsupported phase measured nothing; it did not measure zero."""
    never = phase(
        PHASE_RETRIEVAL_EXTENDED,
        status=PHASE_UNSUPPORTED,
        run_id=None,
        reason="this build cannot run it",
    )

    summary = summarize_phase(never)

    assert summary["items"] is None
    assert summary["retrieval"] is None
    assert summary["answer_quality"] is None
    assert summary["failure_attribution"] is None
    assert summary["latency_ms"]["source"] is None
    assert summary["reason"] == "this build cannot run it"
    assert summary["status"] == PHASE_UNSUPPORTED


def test_a_partial_benchmark_keeps_the_phases_that_finished():
    """A benchmark still running summarizes what it has so far."""
    finished = phase(results=aggregate([scored_row(latency_ms=20.0)]))
    pending = phase(
        PHASE_END_TO_END_REGULAR, status=PHASE_QUEUED, run_id=None, results=None
    )

    summary = summarize_benchmark(
        benchmark([finished, pending], status="running", finished_at=None),
        runs=[run("run-1", [20.0])],
    )

    assert summary["totals"]["total_phases"] == 2
    assert summary["totals"]["measured_phases"] == 1
    assert summary["totals"]["phase_status_counts"] == {
        PHASE_COMPLETED: 1,
        PHASE_QUEUED: 1,
    }
    assert summary["totals"]["items"]["reached"] == 1
    assert summary["phases"][1]["items"] is None
    assert as_json(summary)


def test_a_malformed_phase_table_is_ignored_rather_than_fatal():
    """The summary is descriptive: a broken document must not raise."""
    summary = summarize_benchmark({"phases": "not a list"})

    assert summary["phases"] == []


# ── Totals ────────────────────────────────────────────────────────────────

def test_totals_sum_the_denominators_and_pool_the_samples():
    """Item counts and latency samples are the figures a rollup preserves."""
    first = phase(results=aggregate([scored_row(), {"skipped": True}]))
    second = phase(
        PHASE_END_TO_END_REGULAR,
        run_id="run-2",
        results=aggregate([scored_row(), scored_row()], MODE_END_TO_END),
    )

    summary = summarize_benchmark(
        benchmark([first, second]),
        runs=[run("run-1", [10.0, 30.0]), run("run-2", [50.0])],
    )
    totals = summary["totals"]

    assert totals["items"] == {
        "evaluated": 3,
        "skipped": 1,
        "unscorable": 0,
        "guardrail_blocked": 0,
        "failed": 0,
        "reached": 4,
    }
    assert totals["latency_ms"]["sample_count"] == 3
    assert totals["latency_ms"]["mean"] == pytest.approx(30.0)
    assert totals["latency_ms"]["p50"] == pytest.approx(30.0)


def test_execution_and_scoring_axes_account_for_blocked_items_once():
    rows = [scored_row(outcome="success") for _ in range(24)]
    rows.extend({"skipped": True, "outcome": "success"} for _ in range(4))
    rows.extend(
        {"skipped": True, "outcome": "guardrail_blocked", "guardrail_stage": "input"}
        for _ in range(2)
    )

    summary = summarize_phase(phase(results=aggregate(rows)))

    assert summary["execution"] == {
        "total": 30,
        "succeeded": 28,
        "guardrail_blocked": 2,
        "failed": 0,
        "timed_out": 0,
        "interrupted": 0,
    }
    assert summary["scoring"] == {
        "dataset_items": 30,
        "scored": 24,
        "skipped": 6,
        "unscorable": 0,
    }
    assert summary["items"]["reached"] == 30
    assert sum(
        summary["execution"][key]
        for key in (
            "succeeded",
            "guardrail_blocked",
            "failed",
            "timed_out",
            "interrupted",
        )
    ) == summary["execution"]["total"]
    assert summary["execution"]["total"] == summary["scoring"]["dataset_items"]


def test_pooled_axes_do_not_double_count_guardrail_blocks():
    rows = [scored_row(outcome="success") for _ in range(28)] + [
        {"skipped": True, "outcome": "guardrail_blocked"},
        {"skipped": True, "outcome": "guardrail_blocked"},
    ]
    phases = [
        phase(name, run_id=f"run-{index}", results=aggregate(rows))
        for index, name in enumerate(
            (PHASE_RETRIEVAL_BASE, PHASE_RETRIEVAL_EXTENDED, PHASE_END_TO_END_REGULAR),
            start=1,
        )
    ]

    totals = summarize_benchmark(benchmark(phases))["totals"]

    assert totals["execution"]["total"] == 90
    assert totals["execution"]["guardrail_blocked"] == 6
    assert totals["scoring"]["dataset_items"] == 90
    assert totals["items"]["reached"] == 90


@pytest.mark.compat
def test_legacy_results_do_not_infer_execution_outcomes():
    summary = summarize_phase(
        phase(results={"items_evaluated": 24, "items_skipped": 6, "items_failed": 2})
    )

    assert summary["execution"] == {
        "total": None,
        "succeeded": None,
        "guardrail_blocked": None,
        "failed": None,
        "timed_out": None,
        "interrupted": None,
    }
    assert summary["scoring"]["dataset_items"] == 30
    assert summary["items"]["reached"] == 30


def test_totals_carry_no_pooled_retrieval_or_quality_mean():
    """Averaging a retrieval phase with an end-to-end one measures nothing."""
    summary = summarize_benchmark(benchmark([phase(results=aggregate([scored_row()]))]))

    assert "retrieval" not in summary["totals"]
    assert "answer_quality" not in summary["totals"]


# ── Failure attribution ───────────────────────────────────────────────────

def test_attribution_rates_are_recomputed_from_the_pooled_counts():
    """A summed count invalidates a stored rate, so the rate is rebuilt."""
    attributed = {
        "counts": {category: 0 for category in FAILURE_CATEGORIES},
        "rates": {category: 1.0 for category in FAILURE_CATEGORIES},
        "items_attributed": 4,
    }
    attributed["counts"][CATEGORY_RETRIEVAL] = 1

    summary = summarize_benchmark(
        benchmark(
            [
                phase(results={"failure_attribution": attributed}),
                phase(PHASE_END_TO_END_REGULAR, run_id="run-2", results={
                    "failure_attribution": attributed
                }),
            ]
        )
    )

    per_phase = summary["phases"][0]["failure_attribution"]
    totals = summary["totals"]["failure_attribution"]

    assert per_phase["rates"][CATEGORY_RETRIEVAL] == pytest.approx(0.25)
    assert totals["counts"][CATEGORY_RETRIEVAL] == 2
    assert totals["items_attributed"] == 8
    assert totals["rates"][CATEGORY_RETRIEVAL] == pytest.approx(0.25)


def test_attribution_rates_are_null_when_nothing_was_attributable():
    """Zero percent would claim a clean run nobody measured."""
    results = aggregate([{"skipped": True}])

    block = summarize_phase(phase(results=results))["failure_attribution"]

    assert block["items_attributed"] == 0
    assert all(block["rates"][category] is None for category in FAILURE_CATEGORIES)


# ── JSON validity ─────────────────────────────────────────────────────────

def test_non_finite_stored_numbers_become_null():
    """NaN and Infinity survive BSON but are not JSON; they leave as null."""
    poisoned = {
        "recall_at_k": {str(k): float("nan") for k in K_VALUES},
        "mrr": float("inf"),
        "mean_latency_ms": float("-inf"),
        "items_evaluated": 1,
        "answer_quality": {
            "groundedness": {"mean": float("nan"), "counted": 1, "excluded": 0},
            "hallucination_rate": float("nan"),
        },
    }

    summary = summarize_benchmark(
        benchmark([phase(results=poisoned)]),
        runs=[run("run-1", [float("nan"), 10.0])],
    )
    measured = summary["phases"][0]

    assert measured["retrieval"]["recall_at_k"]["5"] is None
    assert measured["retrieval"]["mrr"] is None
    assert measured["answer_quality"]["groundedness"]["mean"] is None
    assert measured["answer_quality"]["hallucination_rate"] is None
    assert measured["latency_ms"]["sample_count"] == 1
    assert as_json(summary)


def test_a_boolean_is_never_read_as_a_metric():
    """True is an int in Python; a score of 1.0 from a flag is fabricated."""
    summary = summarize_phase(phase(results={"mrr": True, "items_evaluated": True}))

    assert summary["retrieval"]["mrr"] is None
    assert summary["items"]["evaluated"] == 0


def test_the_whole_summary_serializes_without_allow_nan():
    """The export writes strict JSON; every path through here must survive it."""
    summary = summarize_benchmark(
        benchmark(
            [
                phase(results=aggregate([scored_row(), {"error": "boom"}])),
                phase(PHASE_RETRIEVAL_EXTENDED, status=PHASE_UNSUPPORTED, run_id=None),
            ]
        ),
        runs=[run("run-1", [1.0, 2.0])],
    )

    restored = json.loads(as_json(summary))

    assert restored["phases"][0]["latency_ms"]["p99"] == pytest.approx(2.0)
    assert not any(
        isinstance(value, float) and not math.isfinite(value)
        for value in restored["totals"]["latency_ms"].values()
        if isinstance(value, float)
    )
