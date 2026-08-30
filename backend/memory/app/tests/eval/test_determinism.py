"""Repeated identical executions must agree on every labelled metric.

The benchmark calls itself AUTHORITATIVE DETERMINISTIC, so this is the test
that keeps that label honest. It first failed because production breaks a
ranking tie on the memory id and the benchmark let those ids come from
`uuid.uuid4()`, which made the order of two equally scored memories — and
therefore nDCG — differ between runs of the same source against the same
dataset.

Independent processes with different `PYTHONHASHSEED` values are the condition
that matters: a same-process repeat cannot expose ordering that is stable
within a process but varies with the interpreter's hash seed, and the harness
is required to be deterministic without callers pinning that variable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.eval.dataset import generate_scenarios
from app.eval.determinism import deterministic_projection
from app.eval.runner import run_deterministic_benchmark

SERVICE_ROOT = Path(__file__).resolve().parents[3]
HASH_SEEDS = ("0", "1", "524287")

_CHILD_PROGRAM = """
import json
import sys

from app.eval.dataset import generate_scenarios
from app.eval.determinism import deterministic_projection
from app.eval.runner import run_deterministic_benchmark

result = run_deterministic_benchmark(generate_scenarios())
json.dump(deterministic_projection(result), sys.stdout, sort_keys=True, allow_nan=False)
"""


def _run_in_fresh_process(hash_seed: str) -> dict:
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = hash_seed
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(SERVICE_ROOT), str(SERVICE_ROOT.parent)]
    )
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_PROGRAM],
        capture_output=True,
        cwd=str(SERVICE_ROOT),
        env=environment,
        text=True,
        timeout=900,
    )
    assert completed.returncode == 0, completed.stderr
    projection: dict = json.loads(completed.stdout)
    return projection


@pytest.fixture(scope="module")
def independent_projections() -> list[dict]:
    return [_run_in_fresh_process(seed) for seed in HASH_SEEDS]


def test_ndcg_is_identical_across_independent_executions(independent_projections):
    first, second, third = (
        projection["metrics"]["stage_c"]["ndcg"] for projection in independent_projections
    )

    # Exact equality, not approximate: a benchmark that only agrees to a
    # rounding tolerance is not the deterministic benchmark it claims to be.
    assert first == second == third


def test_whole_deterministic_payload_is_identical_across_independent_executions(
    independent_projections,
):
    first, second, third = independent_projections

    assert first == second
    assert second == third


def test_repeated_runs_in_one_process_agree_with_independent_runs(independent_projections):
    scenarios = generate_scenarios()

    repeated = [
        deterministic_projection(run_deterministic_benchmark(scenarios)) for _ in range(2)
    ]

    assert repeated[0] == repeated[1]
    assert repeated[0] == independent_projections[0]


def test_projection_keeps_metrics_and_drops_only_wall_clock_fields():
    result = run_deterministic_benchmark(generate_scenarios()[:8])

    projected = deterministic_projection(result)

    assert projected["metrics"] == result["metrics"]
    assert "wall_time_ms" not in projected["provenance"]
    assert "operational_metrics" not in projected["provenance"]
    assert "benchmark_wall_time_ms" not in projected["summary"]["operational_metrics"]
    # Deterministic operational counters stay: only the timings are dropped.
    assert projected["summary"]["operational_metrics"]["model_calls"] == (
        result["summary"]["operational_metrics"]["model_calls"]
    )
    assert all("agent_latency_ms" not in row["stage_d"] for row in projected["per_scenario"])


def test_ranking_ties_do_not_depend_on_random_identifiers():
    # `scope_coexistence-012-en` is the scenario the original defect was
    # isolated on: two memories score identically, so their order came down to
    # whichever uuid4 happened to sort higher that run.
    tied = [
        scenario
        for scenario in generate_scenarios()
        if scenario.scenario_id == "scope_coexistence-012-en"
    ]
    assert tied, "the tie-breaking scenario must stay in the dataset"

    orderings = {
        tuple(
            tuple(row["actual_ids"])
            for row in run_deterministic_benchmark(tied)["per_scenario"][0]["stage_c"]
        )
        for _ in range(5)
    }

    assert len(orderings) == 1
