"""The contract for which benchmark output must reproduce exactly.

A run of the deterministic benchmark mixes two kinds of number: labelled
evaluation metrics, which are a property of the source, the dataset and the
deterministic stubs alone, and operational latencies, which are a property of
the machine that happened to run it. Only the first kind can be compared
between runs, so this module names the second kind explicitly and projects it
away, rather than leaving each caller to guess which fields to ignore.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Mapping

# Wall-clock measurements. These are reported, never compared: two identical
# runs are expected to disagree here.
OPERATIONAL_METRIC_FIELDS = frozenset(
    {
        "candidate_extraction_llm_latency_ms",
        "persistence_latency_ms_mean",
        "retrieval_latency_ms_mean",
        "memory_agent_latency_ms_mean",
        "benchmark_wall_time_ms",
    }
)

# Per-scenario timing recorded alongside the agent trajectory.
OPERATIONAL_SCENARIO_FIELDS = frozenset({"agent_latency_ms"})

# Top-level provenance entries that are timing, not evaluation output.
OPERATIONAL_PROVENANCE_FIELDS = frozenset({"wall_time_ms", "operational_metrics"})


def _without_timing(operational: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in operational.items()
        if key not in OPERATIONAL_METRIC_FIELDS
    }


def deterministic_projection(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the part of one benchmark result that repeated runs must match.

    Everything survives except wall-clock timing: the manifest, all five stages
    of metrics, every per-scenario row (including the retrieved id ordering
    that nDCG is computed from), the error list, and the non-timing provenance
    that says what was measured and with which stubs.
    """
    projected: Dict[str, Any] = {
        "manifest": copy.deepcopy(dict(result["manifest"])),
        "metrics": copy.deepcopy(dict(result["metrics"])),
        "errors": copy.deepcopy(list(result["errors"])),
    }

    summary = dict(result["summary"])
    summary["operational_metrics"] = _without_timing(summary.get("operational_metrics") or {})
    projected["summary"] = copy.deepcopy(summary)

    provenance = {
        key: value
        for key, value in result["provenance"].items()
        if key not in OPERATIONAL_PROVENANCE_FIELDS
    }
    projected["provenance"] = copy.deepcopy(provenance)

    scenarios = []
    for row in result["per_scenario"]:
        scenario = copy.deepcopy(dict(row))
        stage_d = dict(scenario.get("stage_d") or {})
        for field in OPERATIONAL_SCENARIO_FIELDS:
            stage_d.pop(field, None)
        scenario["stage_d"] = stage_d
        scenarios.append(scenario)
    projected["per_scenario"] = scenarios

    return projected
