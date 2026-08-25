"""Tenant-scoped ingestion metrics for the admin metrics tab.

Answers three questions about the document pipeline that Prometheus cannot
answer per tenant: how many files sit at each status, how long a whole
ingestion task takes, and which files have been in flight too long.

What this module deliberately does not compute: per-stage durations. The
files database stores ``stage.{extraction,review,chunking,...}`` as state
strings — ``waiting``, ``running``, ``done`` — and never records elapsed
time for a stage. Per-stage timing exists only as the Prometheus histogram
``ragapp_file_processing_duration_seconds``, which the gateway merges into
the pipeline route. Deriving a stage duration from ``updated_at`` deltas
would look authoritative while measuring nothing.

Tenancy: like the rag-side metrics module, this does not reuse the
repository's ``_scope_filter``, which pins ``owner_admin_id`` as well as the
tenant. Admin metrics span every uploader in the tenant — and never more
than one tenant.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import Settings
from app.core.constants import FileAction
from app.db.repository import FileRepository
from app.utils.common import build_message_envelope
from shared.auth import AuthIdentity, identity_from_context

# rag and files validate the window independently; neither trusts the other
# to have done it. The values match the gateway's ``MetricsWindow`` enum.
WINDOW_SECONDS: Dict[str, int] = {
    "1h": 3_600,
    "24h": 86_400,
    "7d": 604_800,
    "30d": 2_592_000,
}

DEFAULT_WINDOW = "24h"

# A file whose status is one of these is mid-pipeline: work is expected to
# be happening. Every value is written by file_ingestion_graph or by
# create_file_document; none is invented here.
IN_FLIGHT_STATUSES = ("started", "processing", "resuming")

# How long a file may sit in an in-flight status before it counts as stuck.
# A module constant rather than a config field, so the caller can override
# it per request without a redeploy.
DEFAULT_STUCK_THRESHOLD_MINUTES = 30
MAX_STUCK_FILES = 50

# The stage keys create_file_document() writes. Listed so the funnel can
# report completion per stage without scanning documents in Python.
STAGE_KEYS = (
    "extraction",
    "review",
    "chunking",
    "summary",
    "embedding",
    "semantic",
    "vector",
    "metadata",
)

STAGE_DONE = "done"

# The ingestion funnel, in order. Each step names the `stage.*` key whose
# `done` state marks it complete; `uploaded` is every file in the window and
# so has no stage key of its own.
#
# A subset of STAGE_KEYS on purpose: review, summary, semantic and metadata
# are real stages but not narrowing ones — a file can finish ingestion
# without them — and putting them in the funnel would show drop-off where
# none occurred.
FUNNEL_STEPS: tuple[tuple[str, Optional[str]], ...] = (
    ("uploaded", None),
    ("extracted", "extraction"),
    ("chunked", "chunking"),
    ("embedded", "embedding"),
    ("indexed", "vector"),
)


class FileMetricsAccessDenied(PermissionError):
    """The caller is not an administrator of the tenant being queried."""


class FileMetricsWindowInvalid(ValueError):
    """The caller supplied a window outside the allow-list."""


def _require_admin() -> AuthIdentity:
    """Return the calling identity, or refuse if it is not an admin.

    Raises:
        FileMetricsAccessDenied: If no identity is bound, or it is not an
            admin. These queries drop the per-uploader ownership boundary,
            so an unidentified caller has no safe answer.
    """
    identity = identity_from_context(required=False)
    if identity is None or not identity.is_admin:
        raise FileMetricsAccessDenied("Administrator role required for metrics queries")
    return identity


def _validate_window(window: Optional[str]) -> str:
    """Validate a window against the allow-list.

    Raises:
        FileMetricsWindowInvalid: If ``window`` is not an allowed value.
    """
    resolved = window or DEFAULT_WINDOW
    if resolved not in WINDOW_SECONDS:
        raise FileMetricsWindowInvalid(f"Unsupported metrics window: {window!r}")
    return resolved


class FileMetricsQueryService:
    """Aggregate the files and file_tasks collections for one tenant."""

    def __init__(self, repository: FileRepository, config: Settings) -> None:
        self.repository = repository
        self.config = config

    # ------------------------------------------------------------------
    # Scoping
    # ------------------------------------------------------------------

    def _match(
        self,
        window: str,
        tenant_id: Optional[str],
        identity: AuthIdentity,
    ) -> Dict[str, Any]:
        """Build the tenant-and-time predicate for a pipeline's first stage.

        An explicit ``tenant_id`` must equal the caller's own. Reading another
        tenant's ingestion metrics is not a feature of this phase.

        Raises:
            FileMetricsAccessDenied: If ``tenant_id`` names another tenant.
        """
        if tenant_id is not None and tenant_id != identity.tenant_id:
            raise FileMetricsAccessDenied("Cross-tenant metrics access denied")
        cutoff = datetime.utcnow() - timedelta(seconds=WINDOW_SECONDS[window])
        return {"tenant_id": identity.tenant_id, "created_at": {"$gte": cutoff}}

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def funnel(self, window: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Return the ingestion funnel counted by status and by stage.

        Statuses are reported exactly as the ingestion graph writes them.
        Nothing is renamed, merged, or normalised on the way out — a status
        this module has never seen still appears in the result.

        `funnel_steps` carries each step's count, how many were lost since the
        previous step, and that loss as a fraction — computed here so the UI
        renders numbers rather than deriving them. The first step's drop-off is
        None (nothing precedes it), and any step whose predecessor was empty is
        None rather than 0.0.

        A negative `dropped` is reported as-is rather than clamped: it means a
        later stage completed for more files than an earlier one, which is a
        real inconsistency worth seeing, not a rendering artefact to hide.
        """
        identity = _require_admin()
        window = _validate_window(window)
        stage_counts = {
            f"stage_{stage}_done": {
                "$sum": {"$cond": [{"$eq": [f"$stage.{stage}", STAGE_DONE]}, 1, 0]}
            }
            for stage in STAGE_KEYS
        }
        pipeline: List[Dict[str, Any]] = [
            {"$match": self._match(window, tenant_id, identity)},
            {
                "$facet": {
                    "by_status": [
                        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}},
                    ],
                    "by_review_status": [
                        {"$group": {"_id": "$review_status", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}},
                    ],
                    "stages": [{"$group": {"_id": None, "files": {"$sum": 1}, **stage_counts}}],
                }
            },
        ]
        facets = _first(self._aggregate_files(pipeline))
        stages = _first(facets.get("stages") or [])
        counts = {
            step: stages.get("files", 0) if key is None else stages.get(f"stage_{key}_done", 0)
            for step, key in FUNNEL_STEPS
        }
        funnel_steps: List[Dict[str, Any]] = []
        previous: Optional[int] = None
        for step, _key in FUNNEL_STEPS:
            count = counts[step]
            dropped = None if previous is None else previous - count
            funnel_steps.append(
                {
                    "step": step,
                    "count": count,
                    "dropped": dropped,
                    "drop_off": None if dropped is None else _ratio(dropped, previous),
                    "share_of_uploaded": _ratio(count, counts["uploaded"]),
                }
            )
            previous = count
        return {
            "files": stages.get("files", 0),
            "by_status": [
                {"status": row.get("_id"), "count": row.get("count", 0)}
                for row in (facets.get("by_status") or [])
            ],
            "by_review_status": [
                {"review_status": row.get("_id"), "count": row.get("count", 0)}
                for row in (facets.get("by_review_status") or [])
            ],
            "stage_completion": [
                {"stage": stage, "done": stages.get(f"stage_{stage}_done", 0)}
                for stage in STAGE_KEYS
            ],
            "funnel_steps": funnel_steps,
        }

    def task_durations(self, window: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Return duration percentiles for completed ingestion tasks.

        Whole-task duration, from ``created_at`` to ``completed_at``. This is
        not a per-stage figure: see the module docstring for why one cannot
        be computed from this data.

        Uses the ``$percentile`` accumulator, which requires MongoDB 7 —
        the version docker-compose pins.
        """
        identity = _require_admin()
        window = _validate_window(window)
        match = self._match(window, tenant_id, identity)
        match["completed_at"] = {"$ne": None}
        pipeline: List[Dict[str, Any]] = [
            {"$match": match},
            {
                "$project": {
                    "duration_seconds": {
                        "$divide": [
                            {"$subtract": ["$completed_at", "$created_at"]},
                            1000,
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "tasks": {"$sum": 1},
                    "mean_seconds": {"$avg": "$duration_seconds"},
                    "percentiles": {
                        "$percentile": {
                            "input": "$duration_seconds",
                            "p": [0.5, 0.95, 0.99],
                            "method": "approximate",
                        }
                    },
                }
            },
        ]
        row = _first(self._aggregate_tasks(pipeline))
        percentiles = row.get("percentiles") or []
        return {
            "tasks": row.get("tasks", 0),
            "mean_seconds": row.get("mean_seconds"),
            "p50_seconds": percentiles[0] if len(percentiles) > 0 else None,
            "p95_seconds": percentiles[1] if len(percentiles) > 1 else None,
            "p99_seconds": percentiles[2] if len(percentiles) > 2 else None,
        }

    def stuck_files(
        self,
        tenant_id: Optional[str] = None,
        threshold_minutes: int = DEFAULT_STUCK_THRESHOLD_MINUTES,
    ) -> Dict[str, Any]:
        """Return files left in an in-flight status past the threshold.

        Deliberately not window-scoped: a file stuck since last week is the
        most interesting one on the page, and a 1h window would hide it.

        Returns:
            The count, the threshold used, and up to ``MAX_STUCK_FILES``
            identifiers. Filenames are included because an operator needs to
            recognise the file; no content is.
        """
        identity = _require_admin()
        if tenant_id is not None and tenant_id != identity.tenant_id:
            raise FileMetricsAccessDenied("Cross-tenant metrics access denied")
        minutes = max(1, int(threshold_minutes or DEFAULT_STUCK_THRESHOLD_MINUTES))
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        pipeline: List[Dict[str, Any]] = [
            {
                "$match": {
                    "tenant_id": identity.tenant_id,
                    "status": {"$in": list(IN_FLIGHT_STATUSES)},
                    "updated_at": {"$lt": cutoff},
                }
            },
            {"$sort": {"updated_at": 1}},
            {"$limit": MAX_STUCK_FILES},
            {
                "$project": {
                    "_id": 0,
                    "file_id": 1,
                    "filename": 1,
                    "status": 1,
                    "current_task_id": 1,
                    "created_at": 1,
                    "updated_at": 1,
                }
            },
        ]
        rows = [_serialize(row) for row in self._aggregate_files(pipeline)]
        return {
            "threshold_minutes": minutes,
            "in_flight_statuses": list(IN_FLIGHT_STATUSES),
            "count": len(rows),
            "truncated": len(rows) >= MAX_STUCK_FILES,
            "files": rows,
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def handle_get_metrics(
        self,
        correlation_id: Optional[str],
        request: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run every ingestion section and wrap the result in a reply envelope.

        Args:
            correlation_id: The RabbitMQ correlation id for this request.
            request: The inbound request envelope. Recognised payload keys
                are ``window``, ``tenant_id``, and ``threshold_minutes``.

        Returns:
            A reply envelope. On refusal or an invalid window it carries
            ``success: False`` and a structured error rather than raising,
            so the gateway sees a normal failed reply.
        """
        payload = dict(request.get("payload") or {})
        window = payload.get("window") or request.get("window")
        tenant_id = payload.get("tenant_id") or request.get("tenant_id")
        threshold = (
            payload.get("threshold_minutes")
            or request.get("threshold_minutes")
            or DEFAULT_STUCK_THRESHOLD_MINUTES
        )
        try:
            data: Dict[str, Any] = {
                # The tenant these pipelines actually ran against.
                "tenant_id": _require_admin().tenant_id,
                "funnel": self.funnel(window, tenant_id),
                "task_durations": self.task_durations(window, tenant_id),
                "stuck_files": self.stuck_files(tenant_id, threshold),
            }
        except (FileMetricsAccessDenied, FileMetricsWindowInvalid) as exc:
            return self._envelope(correlation_id, request, {}, error=str(exc))
        return self._envelope(correlation_id, request, data)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _aggregate_files(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate the primary files collection."""
        return list(self.repository.collection.aggregate(pipeline))

    def _aggregate_tasks(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate the file_tasks collection."""
        collection = self.repository._require_collection(
            self.repository.file_tasks_collection, "file_tasks"
        )
        return list(collection.aggregate(pipeline))

    def _envelope(
        self,
        correlation_id: Optional[str],
        request: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the shared reply envelope for a metrics request."""
        return build_message_envelope(
            message_type="reply",
            action=request.get("action") or FileAction.GET_METRICS.value,
            source_service=self.config.service_name,
            target_service=request.get("source_service") or "gateway",
            request_id=request.get("request_id"),
            trace_id=request.get("trace_id"),
            correlation_id=correlation_id,
            payload=payload,
            success=error is None,
            error=None if error is None else {"code": "metrics_denied", "message": error},
        )


def _first(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the single row of a ``_id: None`` group, or an empty dict."""
    return rows[0] if rows else {}


def _ratio(numerator: float, denominator: float) -> Optional[float]:
    """Divide, returning None rather than 0.0 when there is nothing to divide.

    A drop-off over zero inbound files is unknown, not zero. Returning 0.0
    would render a confident "0% lost" for a stage nothing ever reached.
    """
    if not denominator:
        return None
    return numerator / denominator


def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
    """Make one projected file row JSON-safe for the reply envelope."""
    return {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in row.items()
    }
