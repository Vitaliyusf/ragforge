"""Compatibility lane: eval snapshots written before snapshot versioning existed.

Retire together with the production pre-version snapshot read path."""
from __future__ import annotations

import pytest


from shared.context import bound_context

from app.tests.eval._harness import (
    ADMIN,
    build,
    execute,
)


pytestmark = pytest.mark.compat
def test_a_stored_snapshot_written_before_versioning_reads_back_as_version_one():
    """Older run documents stay readable. The legacy keys are left exactly as
    that run recorded them — they are its provenance — and the stamp is what
    tells a reader to interpret them as config's declaration rather than as a
    claim about what ran."""
    store, runner, _, dataset_id = build()
    run = execute(runner, dataset_id)
    legacy_snapshot = {"top_k_documents": 6, "reranker_enabled": True}
    with bound_context(**ADMIN.to_dict()):
        stored = store._find_one(
            store.config.eval_runs_collection,
            {"tenant_id": ADMIN.tenant_id, "run_id": run["run_id"]},
        )
        stored["config_snapshot"] = legacy_snapshot

        snapshot = store.get_run(run["run_id"])["config_snapshot"]

    assert snapshot["snapshot_version"] == 1
    assert snapshot["reranker_enabled"] is True
    assert snapshot["top_k_documents"] == 6


