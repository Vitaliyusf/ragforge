"""Run a dataset through every supported benchmark phase in one workflow.

A "full diagnostic benchmark" is not a new kind of measurement. It is the
eval runs an admin would otherwise start by hand, one after another, in an
order somebody has to remember, with the expensive ones started only if the
cheap ones proved the system is up. This module is that sequence, executed
server-side, with a document that says at every moment which phase is running
and what the finished ones produced.

**Every phase is an ordinary eval run.** Each one is opened through
:meth:`EvalRunner.open_run` and stored in the same ``eval_runs`` collection,
carrying the ``benchmark_id`` it belongs to. There is no second scoring path,
no benchmark-only aggregation and no parallel notion of a result: a phase's
numbers and a hand-started run's numbers are produced by the same code, which
is the only way the two can be compared.

**Evaluation mode and pipeline mode are separate axes.** ``retrieval`` versus
``end_to_end`` says how much of the stack a phase measured. ``regular``
versus ``extended`` says which variant of the conversation pipeline it drove.
A phase is a point in that grid, and the grid is why the two are not one
enumeration — "extended" as a single value cannot distinguish a deeper
pipeline from a more expensive measurement.

**Only phases this build can actually run are executed.** The catalogue below
includes a phase the current implementation cannot honour — extended-pipeline
retrieval — because the retrieval eval issues one ``search_chunks`` call the
conversation pipeline never sees. Running it would produce the base numbers
under an extended label, which is worse than not running it: it is a
fabricated comparison. It is therefore recorded as ``unsupported`` with the
reason, and the phase that does measure extended-pipeline retrieval —
``end_to_end_extended``, which scores the graph's own sources — is the one
that runs.

Phase order is cheapest first. A systemic failure in the free retrieval phase
— embeddings down, labels rotted — aborts the remaining phases rather than
spending tokens proving the same outage twice, and the phases never reached
are recorded as ``skipped`` with the reason instead of as failures they never
suffered.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from app.core.config import RAGConfig
from app.services.benchmark_manifest import build_benchmark_manifest
from app.services.benchmark_export import build_benchmark_export
from app.services.benchmark_prometheus import (
    BenchmarkPrometheusSnapshotter,
    NullBenchmarkPrometheusSnapshotter,
)
from app.services.eval_runner import (
    ERROR_FORBIDDEN,
    ERROR_NOT_FOUND,
    ERROR_VALIDATION,
    MODE_END_TO_END,
    MODE_RETRIEVAL,
    PIPELINE_EXTENDED,
    PIPELINE_REGULAR,
    EvalRunner,
    error_reply,
)
from app.services.eval_store import (
    BENCHMARK_COMPLETED,
    BENCHMARK_FAILED,
    BENCHMARK_INTERRUPTED,
    BENCHMARK_PARTIAL,
    BENCHMARK_QUEUED,
    BENCHMARK_RUNNING,
    RUN_FAILED,
    EvalAccessDenied,
    EvalNotFound,
    EvalStore,
    EvalValidationError,
    benchmark_dataset_snapshot,
)
from shared.auth import AuthIdentity, identity_from_context
from shared.context import bound_context

# Action strings, mirrored as literals in the gateway's core/constants.py for
# the same reason the eval actions are: the rag service cannot import gateway
# code, so the two lists are kept in step by hand.
START_BENCHMARK_RUN = "start_benchmark_run"
LIST_BENCHMARK_RUNS = "list_benchmark_runs"
GET_BENCHMARK_RUN = "get_benchmark_run"
EXPORT_BENCHMARK_RUN = "export_benchmark_run"

BENCHMARK_ACTIONS = frozenset(
    {
        START_BENCHMARK_RUN,
        LIST_BENCHMARK_RUNS,
        GET_BENCHMARK_RUN,
        EXPORT_BENCHMARK_RUN,
    }
)

# Per-phase states.
#
# `queued` and `running` are the live ones. The rest are terminal and each
# means something the others do not:
#   - `completed`  every item was measured;
#   - `partial`    the phase produced numbers, but some items errored and are
#                  excluded from them — real evidence with a smaller
#                  denominator, not a failure;
#   - `failed`     the phase produced no usable numbers at all;
#   - `skipped`    never attempted, because an earlier phase failed
#                  systemically;
#   - `unsupported` this build cannot run it truthfully;
#   - `interrupted` the orchestration was cancelled while it was running.
PHASE_QUEUED = "queued"
PHASE_RUNNING = "running"
PHASE_COMPLETED = "completed"
PHASE_PARTIAL = "partial"
PHASE_FAILED = "failed"
PHASE_SKIPPED = "skipped"
PHASE_UNSUPPORTED = "unsupported"
PHASE_INTERRUPTED = "interrupted"

# Phase names.
PHASE_RETRIEVAL_BASE = "retrieval_base"
PHASE_RETRIEVAL_EXTENDED = "retrieval_extended"
PHASE_END_TO_END_REGULAR = "end_to_end_regular"
PHASE_END_TO_END_EXTENDED = "end_to_end_extended"

_RETRIEVAL_IS_PIPELINE_INDEPENDENT = (
    "Retrieval-mode evaluation issues a single search that the conversation "
    "pipeline does not influence, so this phase would report the base "
    "retrieval numbers under an extended label. Use end_to_end_extended, "
    "which scores the extended pipeline's own sources."
)
_NO_GRAPH = (
    "No conversation graph is wired into this service, so no phase that "
    "generates an answer can run."
)


@dataclass(frozen=True)
class PhaseSpec:
    """One point in the (evaluation mode x pipeline mode) grid.

    Args:
        name: Stable identifier, stored on the benchmark and safe to key a UI
            on.
        evaluation_mode: ``retrieval`` or ``end_to_end``.
        pipeline_mode: ``regular``, ``extended``, or ``None`` for a phase that
            drives no conversation pipeline.
        requires_graph: Whether the phase needs a wired conversation graph.
        unsupported_reason: Set when this build cannot run the phase
            truthfully regardless of what is wired. It is a property of the
            implementation, not of the deployment, and it is stated in full
            so the answer to "why is this blank" is on the document itself.
    """

    name: str
    evaluation_mode: str
    pipeline_mode: Optional[str]
    requires_graph: bool = False
    unsupported_reason: Optional[str] = None


# Cheapest first: a free phase that fails tells you the system is down before
# an expensive one spends tokens discovering the same thing.
PHASE_SPECS: Tuple[PhaseSpec, ...] = (
    PhaseSpec(PHASE_RETRIEVAL_BASE, MODE_RETRIEVAL, None),
    PhaseSpec(
        PHASE_RETRIEVAL_EXTENDED,
        MODE_RETRIEVAL,
        PIPELINE_EXTENDED,
        unsupported_reason=_RETRIEVAL_IS_PIPELINE_INDEPENDENT,
    ),
    PhaseSpec(
        PHASE_END_TO_END_REGULAR,
        MODE_END_TO_END,
        PIPELINE_REGULAR,
        requires_graph=True,
    ),
    PhaseSpec(
        PHASE_END_TO_END_EXTENDED,
        MODE_END_TO_END,
        PIPELINE_EXTENDED,
        requires_graph=True,
    ),
)

PHASE_NAMES: Tuple[str, ...] = tuple(spec.name for spec in PHASE_SPECS)
_SPECS_BY_NAME: Dict[str, PhaseSpec] = {spec.name: spec for spec in PHASE_SPECS}


def _now_iso() -> str:
    """Current UTC time as an ISO-8601 string.

    Phase timestamps are stored as strings rather than datetimes because they
    live inside an array the document serializer does not descend into, and a
    raw datetime there would reach the RPC reply unserialized.
    """
    return datetime.now(timezone.utc).isoformat()


def unsupported_reason(spec: PhaseSpec, *, graph_available: bool) -> Optional[str]:
    """Why this build cannot run ``spec``, or ``None`` if it can.

    The implementation's own limitation is reported before the deployment's:
    a phase this code cannot honour truthfully stays unsupported even on a
    service with everything wired.
    """
    if spec.unsupported_reason:
        return spec.unsupported_reason
    if spec.requires_graph and not graph_available:
        return _NO_GRAPH
    return None


def plan_phases(
    requested: Optional[List[str]],
    *,
    graph_available: bool,
) -> List[Dict[str, Any]]:
    """Build the phase table a benchmark will execute.

    Every selected phase appears in the result, including the ones that
    cannot run: a benchmark that silently omitted them would look complete
    while having measured less than it claims.

    Args:
        requested: Phase names to include, or ``None`` for the whole
            catalogue. Order is always :data:`PHASE_SPECS` order, not the
            caller's — the sequence is a property of cost, not of the
            request.
        graph_available: Whether a conversation graph is wired.

    Returns:
        Phase records in execution order, each already carrying either
        ``queued`` or ``unsupported`` with its reason.

    Raises:
        EvalValidationError: On an unknown phase name, or when nothing in the
            selection can run.
    """
    if requested is not None:
        unknown = [name for name in requested if name not in _SPECS_BY_NAME]
        if unknown:
            raise EvalValidationError(
                f"Unknown benchmark phase(s): {', '.join(sorted(set(unknown)))}. "
                f"Known phases: {', '.join(PHASE_NAMES)}"
            )
        if not requested:
            raise EvalValidationError("No benchmark phases were requested")
    selected = set(requested) if requested is not None else set(PHASE_NAMES)

    phases: List[Dict[str, Any]] = []
    for spec in PHASE_SPECS:
        if spec.name not in selected:
            continue
        reason = unsupported_reason(spec, graph_available=graph_available)
        phases.append(
            {
                "name": spec.name,
                "evaluation_mode": spec.evaluation_mode,
                "pipeline_mode": spec.pipeline_mode,
                "status": PHASE_UNSUPPORTED if reason else PHASE_QUEUED,
                "reason": reason,
                "run_id": None,
                "started_at": None,
                "finished_at": None,
                "error": None,
                "results": None,
            }
        )

    if not any(phase["status"] == PHASE_QUEUED for phase in phases):
        raise EvalValidationError(
            "No requested benchmark phase can run on this service: "
            + "; ".join(
                f"{phase['name']}: {phase['reason']}"
                for phase in phases
                if phase["reason"]
            )
        )
    return phases


def build_progress(phases: List[Dict[str, Any]], item_count: int) -> Dict[str, Any]:
    """Count the phase table into the progress block.

    ``items_total`` counts only the phases that can run. Including a phase
    this build refuses to execute would put a denominator on the page that
    can never be reached.
    """
    executable = [
        phase
        for phase in phases
        if phase["status"] not in (PHASE_UNSUPPORTED,)
    ]
    item_progress = _item_progress(phases)
    return {
        "total_phases": len(phases),
        "executable_phases": len(executable),
        "completed_phases": _count(phases, PHASE_COMPLETED),
        "partial_phases": _count(phases, PHASE_PARTIAL),
        "failed_phases": _count(phases, PHASE_FAILED),
        "skipped_phases": _count(phases, PHASE_SKIPPED),
        "unsupported_phases": _count(phases, PHASE_UNSUPPORTED),
        "interrupted_phases": _count(phases, PHASE_INTERRUPTED),
        "current_phase": next(
            (phase["name"] for phase in phases if phase["status"] == PHASE_RUNNING),
            None,
        ),
        "items_per_phase": item_count,
        "items_total": item_count * len(executable),
        **item_progress,
    }


def initial_phase_progress(item_count: int, started_at: str) -> Dict[str, Any]:
    """The truthful zero/N state for one phase before its first completion."""
    return {
        "items_completed": 0,
        "items_in_flight": item_count,
        "items_succeeded": 0,
        "items_guardrail_blocked": 0,
        "items_failed": 0,
        "items_timed_out": 0,
        "phase_started_at": started_at,
        "last_progress_at": started_at,
    }


def _item_progress(phases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sum persisted per-phase terminal counters without inventing an item order."""
    keys = (
        "items_completed",
        "items_succeeded",
        "items_guardrail_blocked",
        "items_failed",
        "items_timed_out",
    )
    totals = {key: 0 for key in keys}
    active: Optional[Dict[str, Any]] = None
    last_progress_at: Optional[str] = None
    for phase in phases:
        progress = phase.get("item_progress") or {}
        if progress:
            for key in keys:
                totals[key] += int(progress.get(key) or 0)
        else:
            # Legacy phase records predate item-level counters. Their final
            # aggregate is the only evidence available, so retain it safely.
            totals["items_completed"] += _phase_item_count(phase)
            results = phase.get("results") or {}
            totals["items_guardrail_blocked"] += int(
                results.get("items_guardrail_blocked") or 0
            )
            totals["items_failed"] += int(results.get("items_failed") or 0)
            totals["items_succeeded"] += int(results.get("items_evaluated") or 0)
        if phase.get("status") == PHASE_RUNNING:
            active = progress
        timestamp = progress.get("last_progress_at")
        if timestamp and (last_progress_at is None or timestamp > last_progress_at):
            last_progress_at = timestamp
    return {
        **totals,
        "items_in_flight": int((active or {}).get("items_in_flight") or 0),
        "phase_started_at": (active or {}).get("phase_started_at"),
        "last_progress_at": last_progress_at,
    }


def _item_outcome_key(row: Dict[str, Any]) -> str:
    """Map an eval row's mutually exclusive terminal outcome to a counter."""
    if row.get("outcome") == "timed_out":
        return "items_timed_out"
    if row.get("outcome") == "guardrail_blocked":
        return "items_guardrail_blocked"
    if row.get("outcome") == "failed":
        return "items_failed"
    return "items_succeeded"


def benchmark_status(phases: List[Dict[str, Any]]) -> str:
    """The benchmark's terminal state, read off its finished phase table.

    ``partial`` is the honest answer whenever some phases produced evidence
    and some did not — including a phase that ran with item failures.
    Reporting that as ``completed`` would put a phase nobody measured on a
    chart; reporting it as ``failed`` would discard the phases that worked.
    """
    if any(phase["status"] == PHASE_INTERRUPTED for phase in phases):
        return BENCHMARK_INTERRUPTED
    produced = [
        phase
        for phase in phases
        if phase["status"] in (PHASE_COMPLETED, PHASE_PARTIAL)
    ]
    if not produced:
        return BENCHMARK_FAILED
    degraded = any(
        phase["status"] in (PHASE_PARTIAL, PHASE_FAILED, PHASE_SKIPPED)
        for phase in phases
    )
    return BENCHMARK_PARTIAL if degraded else BENCHMARK_COMPLETED


def _count(phases: List[Dict[str, Any]], status: str) -> int:
    return sum(1 for phase in phases if phase["status"] == status)


def _phase_item_count(phase: Dict[str, Any]) -> int:
    """How many items one finished phase actually got through.

    Every row an eval run writes lands in exactly one of the outcome counters,
    so their sum is the number of items the phase reached — zero for a phase
    refused before scoring, which is what a stale-label failure looks like.
    """
    results = phase.get("results") or {}
    return sum(
        int(results.get(key) or 0)
        for key in (
            "items_evaluated",
            "items_skipped",
            "items_unscorable",
            "items_guardrail_blocked",
            "items_failed",
        )
    )


class BenchmarkRunner:
    """Execute a dataset's supported benchmark phases as one workflow."""

    def __init__(
        self,
        config: RAGConfig,
        store: EvalStore,
        eval_runner: EvalRunner,
        logger: Any = None,
        snapshotter: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.store = store
        # The one and only scorer. A benchmark phase is an eval run; giving
        # this class its own retrieval or aggregation path would create a
        # second set of numbers nobody could reconcile with the first.
        self.eval_runner = eval_runner
        self.logger = logger
        self.snapshotter = snapshotter or NullBenchmarkPrometheusSnapshotter()
        self.owner_id = f"benchmark-{uuid4()}"
        # Strong references to in-flight orchestrations, for the reason
        # `EvalRunner` keeps them: asyncio holds only a weak reference to a
        # task, and a collected orchestration would stop mid-phase.
        self._tasks: Set[asyncio.Task] = set()

    async def reconcile_startup(self) -> None:
        """Make persisted in-process work truthful after a process restart.

        The current runner has no durable per-item checkpoint from which it
        can safely replay a phase.  We therefore preserve terminal phase
        evidence and explicitly interrupt every unresolved phase, never
        creating another eval run for a stored ``run_id``.
        """
        recovered = self.eval_runner.recover_stale_runs()
        recovered_ids = {str(run.get("run_id")) for run in recovered}
        stale_benchmarks = {
            str(benchmark["benchmark_id"]): benchmark
            for benchmark in self.store.stale_benchmarks()
        }
        for benchmark in self.store.active_benchmarks():
            if str(benchmark["benchmark_id"]) not in stale_benchmarks:
                self._log(
                    "benchmark_runner:recovery",
                    "Fresh lease kept",
                    {"benchmark_id": benchmark.get("benchmark_id")},
                )
        for benchmark in stale_benchmarks.values():
            phases = [dict(phase) for phase in benchmark.get("phases") or []]
            changed = False
            for phase in phases:
                if phase.get("status") in (PHASE_COMPLETED, PHASE_PARTIAL, PHASE_FAILED,
                                           PHASE_SKIPPED, PHASE_UNSUPPORTED, PHASE_INTERRUPTED):
                    self._log(
                        "benchmark_runner:recovery",
                        "Completed phase preserved",
                        {"benchmark_id": benchmark.get("benchmark_id"), "phase": phase.get("name")},
                    )
                    continue
                # A nonterminal phase is never replayed on startup.  Its
                # existing run_id is durable duplicate-prevention evidence;
                # no run_id means the former worker did not reach a safe
                # ownership boundary either.
                phase["status"] = PHASE_INTERRUPTED
                phase["finished_at"] = phase.get("finished_at") or _now_iso()
                phase["reason"] = (
                    "Recovery could not prove a safe idempotent resume boundary"
                )
                changed = True
            if not changed and str(benchmark.get("status")) != BENCHMARK_QUEUED:
                self._log(
                    "benchmark_runner:recovery",
                    "Duplicate recovery skipped",
                    {"benchmark_id": benchmark.get("benchmark_id")},
                )
                continue
            tenant_id = str(benchmark["tenant_id"])
            item_count = int((benchmark.get("progress") or {}).get("items_total") or 0)
            self.store.finish_benchmark_run(
                str(benchmark["benchmark_id"]), tenant_id,
                status=BENCHMARK_INTERRUPTED, phases=phases,
                progress=build_progress(phases, item_count),
                error="Benchmark interrupted during process restart; safe resume was not proven",
            )
            self._log(
                "benchmark_runner:recovery",
                "Benchmark interrupted after reconciliation",
                {"benchmark_id": benchmark.get("benchmark_id"),
                 "recovered_eval_runs": sum(1 for phase in phases if str(phase.get("run_id")) in recovered_ids)},
            )

    @property
    def graph_available(self) -> bool:
        """Whether answer-generating phases can run on this service."""
        return self.eval_runner.graph_runner is not None

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def handle(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one benchmark RPC action.

        Refusals travel under ``eval_error`` exactly as the eval actions'
        do, so the gateway's existing translation turns a mistyped dataset
        into a 400 that names it rather than a generic 500.
        """
        try:
            if action == START_BENCHMARK_RUN:
                phases = payload.get("phases")
                return {
                    "benchmark": await self.start_benchmark(
                        str(payload.get("dataset_id") or ""),
                        [str(name) for name in phases] if phases is not None else None,
                    )
                }
            if action == LIST_BENCHMARK_RUNS:
                return {
                    "benchmarks": self.store.list_benchmark_runs(
                        payload.get("dataset_id"), payload.get("limit") or 0
                    )
                }
            if action == GET_BENCHMARK_RUN:
                return {
                    "benchmark": self.store.get_benchmark_run(
                        str(payload.get("benchmark_id") or "")
                    )
                }
            if action == EXPORT_BENCHMARK_RUN:
                return {
                    "export": build_benchmark_export(
                        self.store, str(payload.get("benchmark_id") or "")
                    )
                }
            return error_reply(
                ERROR_VALIDATION, f"Unsupported benchmark action: {action!r}"
            )
        except EvalValidationError as exc:
            return error_reply(ERROR_VALIDATION, str(exc))
        except EvalNotFound as exc:
            return error_reply(ERROR_NOT_FOUND, str(exc))
        except EvalAccessDenied as exc:
            return error_reply(ERROR_FORBIDDEN, str(exc))

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    async def start_benchmark(
        self,
        dataset_id: str,
        phases: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Plan a benchmark and execute it in the background.

        Returns as soon as the benchmark document exists, carrying its
        ``benchmark_id``. A synchronous RPC would blow the gateway's timeout
        on the first phase, let alone all of them, so the caller polls
        ``get_benchmark_run``.

        Args:
            dataset_id: The dataset every phase executes.
            phases: Which phases to include, or ``None`` for the catalogue.

        Raises:
            EvalValidationError: On an unknown phase, an empty dataset, or a
                selection this build cannot run.
            EvalNotFound: If the dataset does not exist in the tenant.
            EvalAccessDenied: If the caller is not an admin.
        """
        # Raises before anything is written, so a refused request leaves no
        # benchmark document behind.
        dataset = self.store.get_dataset(dataset_id)
        identity = identity_from_context(required=True)
        items = dataset.get("items") or []
        if not items:
            raise EvalValidationError("Dataset has no items to evaluate")

        plan = plan_phases(phases, graph_available=self.graph_available)
        dataset_snapshot = benchmark_dataset_snapshot(dataset)
        benchmark = self.store.create_benchmark_run(
            dataset_id,
            plan,
            build_progress(plan, len(items)),
            # Snapshot, not a reference, for the reason a run snapshots them:
            # the dataset can be edited while later phases are still running,
            # and a benchmark whose phases described different label sets
            # would be uncomparable against itself.
            dataset_version=dataset_snapshot["dataset_version"],
            dataset_sha256=dataset_snapshot["dataset_sha256"],
            dataset_snapshot=dataset_snapshot,
            # Captured here rather than per phase: every phase of one
            # benchmark runs on the same build against the same corpus, and
            # a manifest per phase would invite the reader to compare copies
            # of one fact with each other.
            manifest=build_benchmark_manifest(
                self.config,
                dataset=dataset,
                item_count=len(items),
                phases=[str(phase["name"]) for phase in plan],
            ),
            operational_metrics={"before": None, "after": None},
            owner_id=self.owner_id,
        )

        task = asyncio.create_task(
            self._execute(
                str(benchmark["benchmark_id"]),
                identity,
                dataset_id,
                plan,
                len(items),
                dataset_snapshot,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return benchmark

    async def _execute(
        self,
        benchmark_id: str,
        identity: AuthIdentity,
        dataset_id: str,
        phases: List[Dict[str, Any]],
        item_count: int,
        dataset_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run each queued phase in order and close the benchmark.

        The identity is re-bound explicitly rather than left to task context
        inheritance, for the reason ``EvalRunner.execute_run`` does it: every
        downstream call signs itself from the context, and a lost one would
        surface as an authentication error instead of the real problem.

        Wrapped so that **no exception can leave the benchmark in
        ``running``**, cancellation included — which closes it as
        ``interrupted``, a state that says the phases already finished are
        real and the ones never reached were never attempted.
        """
        tenant_id = identity.tenant_id
        self.store.heartbeat_benchmark(benchmark_id, tenant_id, self.owner_id)
        operational_metrics = {"before": await self._capture_snapshot(), "after": None}
        self.store.record_benchmark_operational_metrics(
            benchmark_id, tenant_id, operational_metrics
        )
        aborted: Optional[str] = None
        try:
            with bound_context(**identity.to_dict()):
                self.store.record_benchmark_progress(
                    benchmark_id,
                    tenant_id,
                    status=BENCHMARK_RUNNING,
                    phases=phases,
                    progress=build_progress(phases, item_count),
                    started=True,
                )
                self.store.heartbeat_benchmark(benchmark_id, tenant_id, self.owner_id)
                for phase in phases:
                    if phase["status"] == PHASE_UNSUPPORTED:
                        continue
                    if aborted:
                        phase["status"] = PHASE_SKIPPED
                        phase["reason"] = aborted
                        continue
                    aborted = await self._run_phase(
                        benchmark_id, tenant_id, dataset_id, phase, phases, item_count,
                        dataset_snapshot,
                    )

            status = benchmark_status(phases)
            operational_metrics["after"] = await self._capture_snapshot()
            self.store.record_benchmark_operational_metrics(
                benchmark_id, tenant_id, operational_metrics
            )
            self.store.finish_benchmark_run(
                benchmark_id,
                tenant_id,
                status=status,
                phases=phases,
                progress=build_progress(phases, item_count),
                error=_first_phase_error(phases) if status != BENCHMARK_COMPLETED else None,
            )
            return {"benchmark_id": benchmark_id, "status": status, "phases": phases}
        except asyncio.CancelledError:
            for phase in phases:
                if phase["status"] in (PHASE_RUNNING, PHASE_QUEUED):
                    phase["status"] = PHASE_INTERRUPTED
                    phase["finished_at"] = phase["finished_at"] or _now_iso()
                    phase["reason"] = "The benchmark was cancelled before this phase finished"
            operational_metrics["after"] = await self._capture_snapshot()
            self.store.record_benchmark_operational_metrics(
                benchmark_id, tenant_id, operational_metrics
            )
            self.store.finish_benchmark_run(
                benchmark_id,
                tenant_id,
                status=BENCHMARK_INTERRUPTED,
                phases=phases,
                progress=build_progress(phases, item_count),
                error="The benchmark was cancelled before it finished",
            )
            raise
        except Exception as exc:  # noqa: BLE001 - the benchmark must always close
            self._log(
                "benchmark_runner:execute",
                "Benchmark run failed",
                {"error": str(exc)},
            )
            operational_metrics["after"] = await self._capture_snapshot()
            self.store.record_benchmark_operational_metrics(
                benchmark_id, tenant_id, operational_metrics
            )
            self.store.finish_benchmark_run(
                benchmark_id,
                tenant_id,
                status=BENCHMARK_FAILED,
                phases=phases,
                progress=build_progress(phases, item_count),
                error=str(exc),
            )
            return {"benchmark_id": benchmark_id, "status": BENCHMARK_FAILED, "phases": phases}

    async def _run_phase(
        self,
        benchmark_id: str,
        tenant_id: str,
        dataset_id: str,
        phase: Dict[str, Any],
        phases: List[Dict[str, Any]],
        item_count: int,
        dataset_snapshot: Dict[str, Any],
    ) -> Optional[str]:
        """Execute one phase to completion, mutating its record in place.

        Returns:
            The reason the remaining phases must be skipped, or ``None`` to
            continue. A phase that produced no usable numbers aborts the
            rest: whatever broke it — the index, the embedder, the labels —
            breaks the expensive phases behind it too, and paying for that
            discovery twice buys nothing.
        """
        phase["status"] = PHASE_RUNNING
        phase["started_at"] = _now_iso()
        phase["item_progress"] = initial_phase_progress(item_count, phase["started_at"])
        self.store.record_benchmark_progress(
            benchmark_id,
            tenant_id,
            status=BENCHMARK_RUNNING,
            phases=phases,
            progress=build_progress(phases, item_count),
        )

        try:
            prepared = await self.eval_runner.open_run(
                dataset_id,
                phase["evaluation_mode"],
                phase["pipeline_mode"],
                benchmark_id=benchmark_id,
                dataset_snapshot=dataset_snapshot,
            )
        except (EvalValidationError, EvalNotFound, EvalAccessDenied) as exc:
            # The phase never opened a run, so there is nothing to attribute
            # the failure to but the phase itself.
            return self._fail_phase(phase, str(exc))

        phase["run_id"] = prepared.run_id
        progress_lock = asyncio.Lock()

        async def record_item(row: Dict[str, Any]) -> None:
            # Eval tasks finish concurrently. Serializing only this small
            # read/modify/write prevents lost increments while retaining the
            # runner's configured retrieval concurrency.
            async with progress_lock:
                progress = phase["item_progress"]
                progress["items_completed"] += 1
                progress["items_in_flight"] -= 1
                progress[_item_outcome_key(row)] += 1
                progress["last_progress_at"] = _now_iso()
                self.store.record_benchmark_progress(
                    benchmark_id,
                    tenant_id,
                    status=BENCHMARK_RUNNING,
                    phases=phases,
                    progress=build_progress(phases, item_count),
                )
                self.store.heartbeat_benchmark(benchmark_id, tenant_id, self.owner_id)

        summary = await prepared.execute(on_item_completed=record_item)
        phase["finished_at"] = _now_iso()
        results = summary.get("results") or {}
        phase["results"] = results

        if summary.get("status") == RUN_FAILED:
            return self._fail_phase(phase, summary.get("error") or "The phase produced no results")

        failed_items = int(results.get("items_failed") or 0)
        if failed_items:
            phase["status"] = PHASE_PARTIAL
            phase["reason"] = (
                f"{failed_items} of {item_count} items failed and are excluded "
                "from this phase's means"
            )
            return None
        phase["status"] = PHASE_COMPLETED
        return None

    def _fail_phase(self, phase: Dict[str, Any], error: str) -> str:
        """Close one phase as failed and report why the rest are skipped."""
        phase["status"] = PHASE_FAILED
        phase["error"] = error
        phase["finished_at"] = phase["finished_at"] or _now_iso()
        return f"Skipped after phase {phase['name']} failed: {error}"

    def _log(self, event: str, message: str, data: Dict[str, Any]) -> None:
        if self.logger is not None:
            self.logger.log(event, message, data)

    async def _capture_snapshot(self) -> Dict[str, Any]:
        """Keep an unexpected collector defect from failing the benchmark."""
        try:
            return await self.snapshotter.capture()
        except Exception as exc:  # noqa: BLE001 - monitoring is optional evidence
            self._log(
                "benchmark_runner:prometheus_snapshot",
                "Prometheus snapshot unavailable",
                {"error": str(exc)},
            )
            return await NullBenchmarkPrometheusSnapshotter().capture()


def _first_phase_error(phases: List[Dict[str, Any]]) -> Optional[str]:
    """The first failed phase's error, used as the benchmark's message."""
    return next(
        (phase["error"] for phase in phases if phase["status"] == PHASE_FAILED),
        None,
    )


def create_benchmark_runner(
    config: RAGConfig,
    store: EvalStore,
    eval_runner: EvalRunner,
    logger: Any = None,
) -> BenchmarkRunner:
    """Create the benchmark orchestrator over an existing eval runner."""
    return BenchmarkRunner(
        config,
        store,
        eval_runner,
        logger,
        snapshotter=BenchmarkPrometheusSnapshotter(config.prometheus_url),
    )
