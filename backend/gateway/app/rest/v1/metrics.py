"""Admin metrics API routes.

Every route is admin-only, accepts ``?window=`` from a fixed allow-list and
an optional ``&tenant_id=``, and returns the shared metrics envelope:

    {"window", "tenant_id", "generated_at", "prometheus_available",
     "prometheus_scope", "data"}

``window`` is typed as :class:`MetricsWindow`, so FastAPI rejects anything
outside the allow-list with a 422 before the value could reach a PromQL
expression or a MongoDB pipeline.

The eval routes below do not use that envelope. It exists for windowed
panels with a Prometheus availability flag, and neither concept applies to
a dataset listing or a run document.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from app.core.auth import require_admin
from app.core.constants import (
    BenchmarkPhase,
    BenchmarkProfile,
    EvalPipelineMode,
    EvalRunMode,
    MetricsWindow,
)
from app.core.deps import get_metrics_service
from app.core.errors import handle_exception
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])

_WINDOW = Query(MetricsWindow.DAY, description="Lookback window")
_TENANT = Query(None, description="Tenant to report on; defaults to your own")

# Mirrors `eval_max_dataset_items` / `eval_max_query_length` in the rag
# service's RAGConfig. Checked here so a malformed upload is refused with a
# field-level 422 before it costs an RPC, and checked again in `eval_store`
# because an RPC caller is not automatically this gateway.
EVAL_MAX_ITEMS = 1000
EVAL_MAX_QUERY_LENGTH = 2000
EVAL_MAX_NAME_LENGTH = 200
EVAL_MAX_INPUT_CHARS = 5 * 1024 * 1024


class EvalItemIn(BaseModel):
    """One golden-set item: a query and the ids judged relevant to it."""

    item_id: Optional[str] = None
    query: str = Field(min_length=1, max_length=EVAL_MAX_QUERY_LENGTH)
    relevant_chunk_ids: List[str] = Field(default_factory=list)
    relevant_file_ids: List[str] = Field(default_factory=list)
    # Read only by an `end_to_end` run. A dataset without them stays a valid
    # retrieval golden set and scores exactly as it did before.
    expected_answer: Optional[str] = Field(default=None, max_length=EVAL_MAX_QUERY_LENGTH)
    expected_claims: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _require_ground_truth(self) -> "EvalItemIn":
        """Refuse an item that cannot be scored.

        Accepting it would silently inflate `items_skipped` on every future
        run while looking like a complete dataset.
        """
        if not self.relevant_chunk_ids and not self.relevant_file_ids:
            raise ValueError(
                "each item needs at least one relevant_chunk_id or relevant_file_id"
            )
        return self


class EvalDatasetCreate(BaseModel):
    """A whole golden set, uploaded as JSON."""

    name: str = Field(min_length=1, max_length=EVAL_MAX_NAME_LENGTH)
    description: Optional[str] = Field(default=None, max_length=EVAL_MAX_QUERY_LENGTH)
    items: List[EvalItemIn] = Field(min_length=1, max_length=EVAL_MAX_ITEMS)


class GoldenSetValidationIn(BaseModel):
    """Raw Golden Set text and its explicitly selected source format."""

    content: str = Field(min_length=1, max_length=EVAL_MAX_INPUT_CHARS)
    format: Literal["json", "jsonl"]


class EvalDatasetImport(GoldenSetValidationIn):
    """A raw Golden Set that should be parsed and stored."""

    name: str = Field(min_length=1, max_length=EVAL_MAX_NAME_LENGTH)
    description: Optional[str] = Field(default=None, max_length=EVAL_MAX_QUERY_LENGTH)


class EvalDatasetUpdate(BaseModel):
    """A rename, a re-description, or a wholesale item replacement."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=EVAL_MAX_NAME_LENGTH)
    description: Optional[str] = Field(default=None, max_length=EVAL_MAX_QUERY_LENGTH)
    items: Optional[List[EvalItemIn]] = Field(default=None, max_length=EVAL_MAX_ITEMS)


class EvalRunCreate(BaseModel):
    """Start a run over one dataset.

    ``mode`` defaults to ``retrieval``: the free, LLM-free run stays what a
    caller gets by saying nothing.
    """

    dataset_id: str = Field(min_length=1)
    mode: EvalRunMode = EvalRunMode.RETRIEVAL
    # Unset by default, and unset is what a retrieval run must send: rag
    # refuses a pipeline mode on a run whose single search no pipeline routes,
    # rather than recording a pipeline the run never drove.
    pipeline_mode: Optional[EvalPipelineMode] = None


class BenchmarkRunCreate(BaseModel):
    """Start a full diagnostic benchmark over one dataset.

    ``phases`` unset means the whole catalogue. Naming phases here does not
    promise they run — rag records the ones this build cannot execute
    truthfully as ``unsupported``, with the reason, instead of producing
    numbers under a label they do not belong to.
    """

    dataset_id: str = Field(min_length=1)
    profile: Optional[BenchmarkProfile] = None
    phases: Optional[List[BenchmarkPhase]] = Field(
        default=None, min_length=1, max_length=len(BenchmarkPhase)
    )

    @model_validator(mode="after")
    def profile_or_phases(self) -> "BenchmarkRunCreate":
        if self.phases is not None and self.profile is not None:
            raise ValueError("Specify a benchmark profile or phases, not both")
        return self


class EvalCostEstimate(BaseModel):
    """Ask what a run would cost before starting it."""

    item_count: int = Field(ge=0, le=EVAL_MAX_ITEMS)
    mode: EvalRunMode = EvalRunMode.RETRIEVAL
    model: Optional[str] = Field(default=None, max_length=EVAL_MAX_NAME_LENGTH)


@router.get("/overview", dependencies=[Depends(require_admin)])
async def metrics_overview(
    window: MetricsWindow = _WINDOW,
    tenant_id: Optional[str] = _TENANT,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """KPI header: turn latency, TTFT, QPS, errors, quality, tokens, cost."""
    try:
        return await service.overview(window, tenant_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/latency", dependencies=[Depends(require_admin)])
async def metrics_latency(
    window: MetricsWindow = _WINDOW,
    tenant_id: Optional[str] = _TENANT,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Latency time series, stage breakdown, HTTP percentiles, RPC timings."""
    try:
        return await service.latency(window, tenant_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/retrieval", dependencies=[Depends(require_admin)])
async def metrics_retrieval(
    window: MetricsWindow = _WINDOW,
    tenant_id: Optional[str] = _TENANT,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Hit rate, score histogram, chunks per query, reranker lift, search p95."""
    try:
        return await service.retrieval(window, tenant_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/quality", dependencies=[Depends(require_admin)])
async def metrics_quality(
    window: MetricsWindow = _WINDOW,
    tenant_id: Optional[str] = _TENANT,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Score distributions, confidence mix, proxy hallucination, worst turns."""
    try:
        return await service.quality(window, tenant_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/pipeline", dependencies=[Depends(require_admin)])
async def metrics_pipeline(
    window: MetricsWindow = _WINDOW,
    tenant_id: Optional[str] = _TENANT,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Ingestion funnel, stage durations, stuck files, throughput, token cost."""
    try:
        return await service.pipeline(window, tenant_id)
    except Exception as exc:
        raise handle_exception(exc)


# ── Eval harness ──────────────────────────────────────────────────────────

@router.get("/eval/datasets", dependencies=[Depends(require_admin)])
async def list_eval_datasets(
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """List golden-set datasets with item counts and last-run times."""
    try:
        return await service.list_eval_datasets()
    except Exception as exc:
        raise handle_exception(exc)


@router.post("/eval/datasets", dependencies=[Depends(require_admin)])
async def create_eval_dataset(
    body: EvalDatasetCreate,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Import one golden set. Malformed items are refused, never truncated."""
    try:
        return await service.create_eval_dataset(
            body.name,
            body.description,
            [item.model_dump() for item in body.items],
        )
    except Exception as exc:
        raise handle_exception(exc)


@router.post("/eval/datasets/validate", dependencies=[Depends(require_admin)])
async def validate_eval_dataset(
    body: GoldenSetValidationIn,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Validate every item that can be checked without storing the upload."""
    try:
        return await service.validate_eval_dataset(body.content, body.format)
    except Exception as exc:
        raise handle_exception(exc)


@router.post("/eval/datasets/import", dependencies=[Depends(require_admin)])
async def import_eval_dataset(
    body: EvalDatasetImport,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Parse and store one bounded JSON/JSONL Golden Set."""
    try:
        return await service.import_eval_dataset(
            body.name,
            body.description,
            body.content,
            body.format,
        )
    except Exception as exc:
        raise handle_exception(exc)


@router.patch("/eval/datasets/{dataset_id}", dependencies=[Depends(require_admin)])
async def update_eval_dataset(
    dataset_id: str,
    body: EvalDatasetUpdate,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Rename a dataset or replace its items."""
    try:
        return await service.update_eval_dataset(
            dataset_id,
            name=body.name,
            description=body.description,
            items=(
                [item.model_dump() for item in body.items]
                if body.items is not None
                else None
            ),
        )
    except Exception as exc:
        raise handle_exception(exc)


@router.delete("/eval/datasets/{dataset_id}", dependencies=[Depends(require_admin)])
async def delete_eval_dataset(
    dataset_id: str,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Delete a dataset. Its past runs are kept as regression evidence."""
    try:
        return await service.delete_eval_dataset(dataset_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.post("/eval/runs", dependencies=[Depends(require_admin)])
async def start_eval_run(
    body: EvalRunCreate,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Start a run, returning its ``run_id`` before it finishes.

    The run executes in the background on the rag service; the client polls
    ``GET /eval/runs/{run_id}`` until the status is terminal.
    """
    try:
        return await service.start_eval_run(
            body.dataset_id,
            body.mode.value,
            body.pipeline_mode.value if body.pipeline_mode else None,
        )
    except Exception as exc:
        raise handle_exception(exc)


@router.post("/eval/benchmarks", dependencies=[Depends(require_admin)])
async def start_benchmark_run(
    body: BenchmarkRunCreate,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Start a full diagnostic benchmark, returning its ``benchmark_id``.

    The phases run sequentially on the rag service, cheapest first, each as an
    ordinary eval run; the client polls ``GET /eval/benchmarks/{id}`` for
    phase-level progress and terminal status.
    """
    try:
        return await service.start_benchmark_run(
            body.dataset_id,
            [phase.value for phase in body.phases] if body.phases else None,
            body.profile.value if body.profile else None,
        )
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/eval/benchmarks", dependencies=[Depends(require_admin)])
async def list_benchmark_runs(
    dataset_id: Optional[str] = Query(None, description="Filter to one dataset"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="How many benchmarks"),
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Benchmark history, newest first."""
    try:
        return await service.list_benchmark_runs(dataset_id, limit)
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/eval/benchmarks/{benchmark_id}", dependencies=[Depends(require_admin)])
async def get_benchmark_run(
    benchmark_id: str,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """One benchmark with its phase table and progress counters."""
    try:
        return await service.get_benchmark_run(benchmark_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.get(
    "/eval/benchmarks/{benchmark_id}/export", dependencies=[Depends(require_admin)]
)
async def export_benchmark_run(
    benchmark_id: str,
    service: MetricsService = Depends(get_metrics_service),
) -> Response:
    """Download the benchmark's safe, tenant-scoped diagnostic ZIP."""
    try:
        exported = await service.export_benchmark_run(benchmark_id)
        archive = exported.get("export") or {}
        content = base64.b64decode(
            str(archive.get("content_base64") or ""), validate=True
        )
        filename = str(archive.get("filename") or "benchmark-export.zip")
        return Response(
            content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise handle_exception(exc)


@router.post("/eval/runs/estimate", dependencies=[Depends(require_admin)])
async def estimate_eval_run_cost(
    body: EvalCostEstimate,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Estimate a run's token spend before it starts.

    Pure arithmetic over the gateway's pricing table — no RPC, no run
    created. An `end_to_end` run is the expensive one, and an admin is shown
    this before they can start it.
    """
    try:
        return service.estimate_eval_cost(body.item_count, body.mode.value, body.model or "")
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/eval/runs", dependencies=[Depends(require_admin)])
async def list_eval_runs(
    dataset_id: Optional[str] = Query(None, description="Filter to one dataset"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="How many runs"),
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """Run history, newest first, without per-item rows."""
    try:
        return await service.list_eval_runs(dataset_id, limit)
    except Exception as exc:
        raise handle_exception(exc)


@router.get("/eval/runs/{run_id}", dependencies=[Depends(require_admin)])
async def get_eval_run(
    run_id: str,
    service: MetricsService = Depends(get_metrics_service),
) -> Dict[str, Any]:
    """One run with its per-item drill-down rows."""
    try:
        return await service.get_eval_run(run_id)
    except Exception as exc:
        raise handle_exception(exc)
