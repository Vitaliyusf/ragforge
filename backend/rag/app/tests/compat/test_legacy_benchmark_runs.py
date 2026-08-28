"""Compatibility lane: benchmark documents written before profiles and manifests existed.

Retire together with the production read paths that tolerate their absence."""
from __future__ import annotations

import pytest


from app.services.benchmark_runner import (
    PHASE_RETRIEVAL_BASE,
    _phase_item_count,
)

from shared.context import bound_context

from app.tests.benchmark._harness import (
    ADMIN,
    build,
    fetch,
    run_benchmark,
)


pytestmark = pytest.mark.compat
def test_legacy_phase_item_count_does_not_add_scoring_and_execution_axes():
    phase = {
        "results": {
            "items_evaluated": 24,
            "items_skipped": 6,
            "items_unscorable": 0,
            "items_guardrail_blocked": 2,
            "items_failed": 0,
        }
    }

    assert _phase_item_count(phase) == 30


def test_a_legacy_benchmark_without_profile_remains_readable():
    store, orchestrator, _, dataset_id = build()
    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    for document in store._memory[store.config.eval_benchmark_runs_collection]:
        document.pop("profile", None)

    assert fetch(store, benchmark["benchmark_id"])["profile"] is None


def test_a_benchmark_recorded_before_manifests_reads_back_as_null():
    """No manifest is invented for a document that never carried one."""
    store, orchestrator, _, dataset_id = build()

    benchmark = run_benchmark(orchestrator, dataset_id, [PHASE_RETRIEVAL_BASE])
    for document in store._memory[store.config.eval_benchmark_runs_collection]:
        document.pop("manifest", None)

    with bound_context(**ADMIN.to_dict()):
        assert store.get_benchmark_run(benchmark["benchmark_id"])["manifest"] is None
        assert store.list_benchmark_runs()[0]["manifest"] is None


