"""Tests for the files-side ingestion metrics aggregation.

The repository double records every pipeline and replays canned rows, which
covers both halves of what matters: the tenant boundary in the first ``$match``,
and the funnel arithmetic built from the aggregation's output.

The funnel numbers below are all hand-computable on purpose — a drop-off that
has to be trusted rather than checked is exactly the figure an operator should
not be shown.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from app.services.metrics_query import (
    FUNNEL_STEPS,
    FileMetricsAccessDenied,
    FileMetricsQueryService,
    FileMetricsWindowInvalid,
)
from shared.auth import AuthIdentity
from shared.context import bound_context

ADMIN = AuthIdentity(tenant_id="tenant-a", user_id="admin-a", role="admin", admin_id="admin-a")
USER = AuthIdentity(tenant_id="tenant-a", user_id="user-a", role="user", admin_id="admin-a")


class RecordingCollection:
    """Record aggregation pipelines and replay canned rows."""

    def __init__(self, rows: List[Dict[str, Any]], log: List[List[Dict[str, Any]]]) -> None:
        self._rows = rows
        self._log = log

    def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self._log.append(pipeline)
        return self._rows


class RecordingRepository:
    """Stand in for FileRepository with a recording files collection."""

    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None) -> None:
        self.pipelines: List[List[Dict[str, Any]]] = []
        self.collection = RecordingCollection(rows or [], self.pipelines)


def build_service(rows: Optional[List[Dict[str, Any]]] = None) -> FileMetricsQueryService:
    """Build the service on a fake repository and config."""
    config = SimpleNamespace(service_name="files")
    return FileMetricsQueryService(RecordingRepository(rows), config)


def facet_rows(stages: Dict[str, int]) -> List[Dict[str, Any]]:
    """Wrap one stage-count row in the ``$facet`` envelope funnel() expects."""
    return [{"by_status": [], "by_review_status": [], "stages": [stages]}]


def funnel_steps(stages: Dict[str, int]) -> List[Dict[str, Any]]:
    """Run funnel() over one canned stage row and return its steps."""
    service = build_service(facet_rows(stages))
    with bound_context(**ADMIN.to_dict()):
        return service.funnel("24h")["funnel_steps"]


# ── Funnel arithmetic ─────────────────────────────────────────────────────

def test_funnel_steps_carry_counts_and_drop_off():
    """Drop-off is computed server-side so two clients cannot derive it two ways."""
    steps = funnel_steps(
        {
            "files": 100,
            "stage_extraction_done": 90,
            "stage_chunking_done": 80,
            "stage_embedding_done": 40,
            "stage_vector_done": 40,
        }
    )

    assert [step["step"] for step in steps] == [name for name, _key in FUNNEL_STEPS]
    assert steps[1] == {
        "step": "extracted",
        "count": 90,
        "dropped": 10,
        "drop_off": pytest.approx(0.1),
        "share_of_uploaded": pytest.approx(0.9),
    }
    # 10 lost out of the 90 that reached chunking — relative to the previous
    # step, not to the 100 uploaded.
    assert steps[2]["drop_off"] == pytest.approx(10 / 90)
    assert steps[2]["share_of_uploaded"] == pytest.approx(0.8)
    # Nothing lost at the last step is a real 0.0, not a missing measurement.
    assert steps[4]["drop_off"] == 0.0


def test_first_funnel_step_has_no_drop_off():
    """Nothing precedes `uploaded`, so its drop-off is None rather than 0."""
    steps = funnel_steps({"files": 10, "stage_extraction_done": 10})

    assert steps[0]["step"] == "uploaded"
    assert steps[0]["dropped"] is None
    assert steps[0]["drop_off"] is None
    assert steps[0]["share_of_uploaded"] == pytest.approx(1.0)


def test_zero_inbound_stage_does_not_divide_by_zero():
    """The empty window: every drop-off is None, and nothing raises.

    `0.0` would render as "0% lost" for a stage nothing ever reached, which is
    the specific wrong answer — it looks like a healthy pipeline rather than an
    idle one.
    """
    steps = funnel_steps(
        {
            "files": 0,
            "stage_extraction_done": 0,
            "stage_chunking_done": 0,
            "stage_embedding_done": 0,
            "stage_vector_done": 0,
        }
    )

    assert [step["count"] for step in steps] == [0, 0, 0, 0, 0]
    assert [step["drop_off"] for step in steps] == [None] * len(FUNNEL_STEPS)
    assert [step["share_of_uploaded"] for step in steps] == [None] * len(FUNNEL_STEPS)


def test_funnel_over_a_window_with_no_rows_at_all():
    """No aggregation rows is a quiet window, not an error."""
    service = build_service([])

    with bound_context(**ADMIN.to_dict()):
        result = service.funnel("24h")

    assert result["files"] == 0
    assert [step["count"] for step in result["funnel_steps"]] == [0] * len(FUNNEL_STEPS)


def test_funnel_reports_a_negative_drop_off_rather_than_hiding_it():
    """A later stage ahead of an earlier one is a real inconsistency.

    Clamping it to zero would hide stage state that genuinely disagrees with
    itself, which is worth surfacing rather than smoothing away.
    """
    steps = funnel_steps(
        {"files": 60, "stage_extraction_done": 50, "stage_chunking_done": 60}
    )

    assert steps[2]["dropped"] == -10
    assert steps[2]["drop_off"] == pytest.approx(-0.2)


def test_stage_completion_is_unchanged_alongside_the_new_steps():
    """The pre-existing stage_completion list keeps its shape."""
    service = build_service(facet_rows({"files": 5, "stage_extraction_done": 4}))

    with bound_context(**ADMIN.to_dict()):
        result = service.funnel("24h")

    completion = {row["stage"]: row["done"] for row in result["stage_completion"]}
    assert completion["extraction"] == 4
    assert completion["summary"] == 0


# ── Tenancy ───────────────────────────────────────────────────────────────

def test_tenant_filter_is_in_the_first_match_stage():
    """Scoping must happen in MongoDB, never by filtering rows in Python."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        service.funnel("24h")

    match = service.repository.pipelines[0][0]["$match"]
    assert match["tenant_id"] == "tenant-a"
    assert "$gte" in match["created_at"]


def test_cross_tenant_access_is_refused():
    """An admin may not read another tenant by passing its id."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        with pytest.raises(FileMetricsAccessDenied):
            service.funnel("24h", tenant_id="tenant-b")


def test_non_admin_is_refused():
    """These pipelines drop the per-uploader boundary, so admin is required."""
    service = build_service()

    with bound_context(**USER.to_dict()):
        with pytest.raises(FileMetricsAccessDenied):
            service.funnel("24h")


def test_unidentified_caller_is_refused():
    """An absent identity is refused as firmly as a non-admin one."""
    service = build_service()

    with pytest.raises(FileMetricsAccessDenied):
        service.funnel("24h")


def test_window_outside_the_allow_list_is_rejected():
    """files validates the window again rather than trusting the gateway."""
    service = build_service()

    with bound_context(**ADMIN.to_dict()):
        with pytest.raises(FileMetricsWindowInvalid):
            service.funnel("all-time")
