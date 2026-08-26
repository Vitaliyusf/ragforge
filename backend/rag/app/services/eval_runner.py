"""Execute a golden-set dataset against live retrieval and score it.

**``retrieval`` mode never calls the LLM, and is the default.** No
generation, no answer evaluation, no reranker-free shortcut. That is what
makes a 200-query run finish in seconds and cost nothing, which in turn is
what makes it usable as a regression gate somebody actually runs before
merging. Nothing in this module may quietly turn that promise into an LLM
bill.

**``end_to_end`` mode runs the whole conversation graph** — generation,
judging, citations — and additionally reports groundedness, hallucination
rate and citation precision/recall over the dataset. It costs real tokens
per item, so it is opt-in per run, recorded in the run's ``config_snapshot``
so a cheap run is never compared against an expensive one as though they
measured the same thing, and bounded by the same ``eval_run_concurrency``
semaphore as retrieval mode.

Graph runs started here are executed with turn-metric recording **off**.
An eval sweep is not user traffic, and letting a few hundred synthetic turns
into ``metrics_turn_facts`` would move the very quality averages the sweep
exists to check.

Retrieval goes through ``ConversationBackendClient.search_chunks`` — the same
call the conversation graph makes — because the number is only meaningful if
it measures the retrieval the application actually performs. Queries are
tagged ``pass_name="eval"`` so downstream services can tell an eval sweep from
live traffic in their own logs.

It asks that call for :func:`candidate_depth` candidates rather than the
production ``top_k_documents``. The two are different quantities: production
depth sizes an answer's context, eval depth is how far down the ranking the
measurement can see. They are kept separate so that tuning one never silently
redefines the other, and the depth a run used is recorded in its
``config_snapshot``.

**Golden-set labels are verified before anything is scored.** A dataset
labelled against an older index can name chunks or files that reindexing or
a chunking change has since removed. Retrieval cannot return an id that no
longer exists, so scoring such a label as a miss reports a recall regression
that never happened — the worst kind, because it looks exactly like a real
one. Each run therefore asks vector_db which of its labelled ids still exist
in its own tenant, records the answer on the run, and refuses to score
against labels the index cannot reach. See :func:`classify_labels` for the
three states a label can be in and :data:`STALE_POLICIES` for what a run
does about them.

Eligibility filtering is replicated here rather than reused from
``ConversationGraph._normalize_chunks``. That method increments the live
``rag_chunks_considered_total`` and ``rag_chunks_filtered_total`` counters,
and an eval sweep pouring hundreds of synthetic chunk decisions into them
would corrupt the retrieval panel those counters feed. The predicate itself —
drop ``review_status == "removed"`` and ``retrieval_allowed == False`` — is
copied exactly, because scoring chunks the app would have refused to use
would measure a retriever that does not exist.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from app.core.config import RAGConfig
from app.services import retrieval_metrics
from app.services.citation_metrics import aggregate_mean
from app.services.conversation_events import CollectingConversationEmitter
from app.services.conversation_types import ConversationRequest
from app.services.eval_store import (
    MODE_END_TO_END,
    MODE_RETRIEVAL,
    RUN_COMPLETED,
    RUN_FAILED,
    EvalAccessDenied,
    EvalNotFound,
    EvalStore,
    EvalValidationError,
    build_config_snapshot,
)
from app.services.failure_attribution import aggregate_attribution, classify_item
from app.services.golden_set_parser import prepare_chunk_labels, prepare_file_labels
from app.services.retrieval_trace import (
    DROP_RETRIEVAL_NOT_ALLOWED,
    DROP_REVIEW_REMOVED,
    STAGE_BASE,
    STAGE_FINAL_CONTEXT,
    RetrievalTrace,
    dropped_view,
)
from shared.auth import AuthIdentity, identity_from_context
from shared.context import bound_context

# The k values every run reports. Deliberately not configurable: they are
# part of the stored `results` shape, and two runs carrying different k sets
# under the same field names would be silently incomparable.
K_VALUES: Tuple[int, ...] = (1, 3, 5, 10, 20)

# Run modes. `retrieval` is the default everywhere it is optional: the
# phase-5 promise of a free run must be what a caller gets by saying
# nothing. The two names are imported from `eval_store` and re-exported for
# the callers that already read them off this module: `build_config_snapshot`
# branches on the mode, and one definition keeps the snapshot and the runner
# from ever disagreeing about how "end_to_end" is spelled.
EVAL_MODES = (MODE_RETRIEVAL, MODE_END_TO_END)

# Which conversation pipeline an `end_to_end` run drives. A **different axis**
# from the evaluation mode above, and deliberately not merged with it: the
# evaluation mode says how much of the stack a run measured, the pipeline mode
# says which variant of the stack it measured. Collapsing them into one
# enumeration is what makes "extended" ambiguous between "a deeper pipeline"
# and "a more expensive measurement".
#
# `None` is a legitimate value, not a missing one: a `retrieval` run issues a
# single pipeline-independent `search_chunks` call, so it drives no pipeline
# at all. Recording `regular` for it would claim a variable the run never set.
PIPELINE_REGULAR = "regular"
PIPELINE_EXTENDED = "extended"
PIPELINE_MODES = (PIPELINE_REGULAR, PIPELINE_EXTENDED)

MATCH_CHUNK = "chunk_id"
MATCH_FILE = "file_id"
MATCH_MIXED = "mixed"

# What a run does when its golden set names labels the index cannot reach.
#
# `fail` is the default. A dataset whose ground truth has rotted is not
# measuring retrieval any more, and the failure mode this feature exists to
# prevent — a confident recall drop caused by relabelling rather than by
# retrieval — is exactly what a partial run would still produce for the
# items it did keep. Nothing in the existing product UX argues for partial
# runs here: a run is cheap to repeat once the labels are fixed.
STALE_POLICY_FAIL = "fail"
# `mark_unscorable` keeps the run and excludes the affected items from every
# mean, reporting them under their own count. It never scores them as
# misses.
STALE_POLICY_UNSCORABLE = "mark_unscorable"
STALE_POLICIES = (STALE_POLICY_FAIL, STALE_POLICY_UNSCORABLE)

# Why a run's labels were not verified, when they were not.
NOT_CHECKED_DISABLED = "disabled"
NOT_CHECKED_NO_LABELS = "no_labels"
NOT_CHECKED_UNAVAILABLE = "unavailable"

# How many retrieved ids one per-item row keeps for the drill-down. Equal to
# max(K_VALUES) so the row always shows every rank the run scores; it is a
# display bound, never applied before scoring.
MAX_ROW_IDS = max(K_VALUES)

# Action strings, mirroring `RagAction` in the gateway's core/constants.py.
# The rag service cannot import gateway code, so they are defined once here
# and the two must stay in step — the same arrangement as METRICS_ACTION.
LIST_EVAL_DATASETS = "list_eval_datasets"
CREATE_EVAL_DATASET = "create_eval_dataset"
VALIDATE_EVAL_DATASET = "validate_eval_dataset"
UPDATE_EVAL_DATASET = "update_eval_dataset"
DELETE_EVAL_DATASET = "delete_eval_dataset"
START_EVAL_RUN = "start_eval_run"
LIST_EVAL_RUNS = "list_eval_runs"
GET_EVAL_RUN = "get_eval_run"

EVAL_ACTIONS = frozenset(
    {
        LIST_EVAL_DATASETS,
        CREATE_EVAL_DATASET,
        VALIDATE_EVAL_DATASET,
        UPDATE_EVAL_DATASET,
        DELETE_EVAL_DATASET,
        START_EVAL_RUN,
        LIST_EVAL_RUNS,
        GET_EVAL_RUN,
    }
)


# Failure kinds the gateway maps onto HTTP status codes.
ERROR_VALIDATION = "validation"
ERROR_NOT_FOUND = "not_found"
ERROR_FORBIDDEN = "forbidden"


def error_reply(kind: str, message: str) -> Dict[str, Any]:
    """Report a refusal without tripping the shared error envelope.

    ``build_reply_envelope`` turns any ``error`` key into an unsuccessful
    reply whose message is the fixed string "RAG request could not be
    completed" and which carries no status code — so the gateway can only
    render it as a 500. That is the wrong answer for an admin who mistyped a
    dataset: they need to be told which item failed and why.

    The refusal therefore travels as a normal reply body under
    ``eval_error``, and ``MetricsService`` raises the matching gateway
    exception. This is a deliberate divergence from ``metrics_query.handle``,
    whose only failure modes are refusals with nothing useful to say.
    """
    return {"eval_error": {"kind": kind, "message": message}}


def relevant_ids(item: Dict[str, Any], match_mode: str) -> Set[str]:
    """The ground-truth ids for one item under the run's match mode.

    Under :data:`MATCH_MIXED` each item uses whichever ids it has, preferring
    chunk ids — a dataset labelled at both granularities is scored at the
    finer one wherever it can be.
    """
    chunk_ids = set(item.get("relevant_chunk_ids") or [])
    file_ids = set(item.get("relevant_file_ids") or [])
    if match_mode == MATCH_CHUNK:
        return chunk_ids
    if match_mode == MATCH_FILE:
        return file_ids
    return chunk_ids or file_ids


def item_match_mode(item: Dict[str, Any], match_mode: str) -> str:
    """Which id field an item was actually scored against."""
    if match_mode != MATCH_MIXED:
        return match_mode
    return MATCH_CHUNK if item.get("relevant_chunk_ids") else MATCH_FILE


def dataset_match_mode(items: List[Dict[str, Any]]) -> str:
    """Choose the run's match mode from how the dataset is labelled.

    Chunk-level matching is preferred because it is what retrieval actually
    ranks. File-level matching is coarser — a chunk from the right file is
    counted as a hit regardless of whether it answers the query — so the mode
    is recorded on the run and two runs using different modes must not be
    compared as the same experiment.
    """
    if all(item.get("relevant_chunk_ids") for item in items):
        return MATCH_CHUNK
    if all(item.get("relevant_file_ids") for item in items):
        return MATCH_FILE
    return MATCH_MIXED


def label_targets(
    items: List[Dict[str, Any]],
    match_mode: str,
) -> Tuple[Set[str], Set[str]]:
    """The chunk ids and file ids a run will actually score against.

    Only the ids that will be *used* are collected. A mixed-mode dataset
    whose item carries both kinds is scored on its chunk ids alone, so
    verifying its file ids would report drift in labels no score depends on.
    """
    chunk_ids: Set[str] = set()
    file_ids: Set[str] = set()
    for item in items:
        ids = relevant_ids(item, match_mode)
        if not ids:
            continue
        if item_match_mode(item, match_mode) == MATCH_CHUNK:
            chunk_ids.update(ids)
        else:
            file_ids.update(ids)
    return chunk_ids, file_ids


def _unreachable_sets(verified: Dict[str, Any], field_name: str) -> Tuple[Set[str], Set[str]]:
    """The missing and present-but-barred ids vector_db reported for one field."""
    report = (verified or {}).get(field_name) or {}
    present = {str(value) for value in report.get("present") or []}
    retrievable = {str(value) for value in report.get("retrievable") or []}
    missing = {str(value) for value in report.get("missing") or []}
    return missing, present - retrievable


@dataclass
class LabelReport:
    """How a run's golden-set labels checked out against the live index.

    ``summary`` is what gets stored on the run and rendered. ``unscorable``
    is the full set of affected item ids, kept in memory only: the stored
    id lists are capped for size, and marking items unscorable from a capped
    list would silently score some of them anyway.
    """

    summary: Dict[str, Any]
    unscorable: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def blocking(self) -> bool:
        """Whether this report must stop the run under its own policy."""
        return (
            self.summary.get("policy") == STALE_POLICY_FAIL
            and bool(self.summary.get("unscorable_item_count"))
        )


def _unchecked_report(reason: str, policy: str, error: Optional[str] = None) -> LabelReport:
    """A report for labels that were never verified.

    Every count is ``None`` rather than ``0``. Zero is a measurement — "we
    looked and found nothing stale" — and claiming it for a check that never
    ran is the one thing a warning state must not do.
    """
    return LabelReport(
        summary={
            "checked": False,
            "reason": reason,
            "error": error,
            "policy": policy,
            "labels_checked": None,
            "stale_label_count": None,
            "stale_item_count": None,
            "stale_ids": [],
            "stale_item_ids": [],
            "unretrievable_label_count": None,
            "unretrievable_item_count": None,
            "unretrievable_ids": [],
            "unscorable_item_count": 0,
            "truncated": False,
        }
    )


def classify_labels(
    items: List[Dict[str, Any]],
    match_mode: str,
    verified: Dict[str, Any],
    *,
    policy: str = STALE_POLICY_FAIL,
    max_reported_ids: int = 50,
) -> LabelReport:
    """Sort every label into valid, stale, or present-but-unreachable.

    Three states, kept apart because they mean different things to whoever
    reads the run:

    - **valid** — the id exists in this tenant's collection and retrieval is
      allowed to return it. Scoring it is meaningful.
    - **stale** — the id is not in the collection at all. Reindexing or a
      chunking change dropped it, or it was never in this tenant. Retrieval
      can never return it, so a miss on it measures nothing.
    - **unreachable** — the id exists but is barred from retrieval by the
      same policy gate search applies (``retrieval_allowed`` false, or a
      ``removed`` review status). Also unscoreable, and reported separately
      because "we deleted it" and "we suppressed it" call for different
      fixes.

    Args:
        items: The dataset's normalized items.
        match_mode: The run's match mode.
        verified: The vector_db reply, keyed ``chunk_ids`` / ``file_ids``.
        policy: One of :data:`STALE_POLICIES`, recorded in the summary.
        max_reported_ids: Cap on each stored id list. Counts stay exact.

    Returns:
        A :class:`LabelReport`.
    """
    missing_chunks, barred_chunks = _unreachable_sets(verified, "chunk_ids")
    missing_files, barred_files = _unreachable_sets(verified, "file_ids")

    stale_ids: Set[str] = set()
    barred_ids: Set[str] = set()
    stale_items: Set[str] = set()
    barred_items: Set[str] = set()
    labels_checked = 0

    for item in items:
        ids = relevant_ids(item, match_mode)
        if not ids:
            continue
        labels_checked += len(ids)
        chunk_level = item_match_mode(item, match_mode) == MATCH_CHUNK
        missing = ids & (missing_chunks if chunk_level else missing_files)
        barred = ids & (barred_chunks if chunk_level else barred_files)
        item_id = str(item.get("item_id") or "")
        if missing:
            stale_ids.update(missing)
            stale_items.add(item_id)
        if barred:
            barred_ids.update(barred)
            barred_items.add(item_id)

    unscorable = stale_items | barred_items
    reported = sorted(unscorable)[:max_reported_ids]
    truncated = (
        len(stale_ids) > max_reported_ids
        or len(barred_ids) > max_reported_ids
        or len(unscorable) > max_reported_ids
    )
    return LabelReport(
        summary={
            "checked": True,
            "reason": None,
            "error": None,
            "policy": policy,
            "labels_checked": labels_checked,
            "stale_label_count": len(stale_ids),
            "stale_item_count": len(stale_items),
            "stale_ids": sorted(stale_ids)[:max_reported_ids],
            "stale_item_ids": reported,
            "unretrievable_label_count": len(barred_ids),
            "unretrievable_item_count": len(barred_items),
            "unretrievable_ids": sorted(barred_ids)[:max_reported_ids],
            "unscorable_item_count": len(unscorable),
            "truncated": truncated,
        },
        unscorable=frozenset(unscorable),
    )


def stale_label_error(summary: Dict[str, Any]) -> str:
    """The message a fail-fast run closes with. Names the counts, not a guess."""
    return (
        f"Refused before scoring: {summary.get('unscorable_item_count')} item(s) "
        f"reference golden-set labels the active index cannot return "
        f"({summary.get('stale_label_count')} label(s) no longer exist, "
        f"{summary.get('unretrievable_label_count')} exist but are excluded from "
        "retrieval). Re-label the dataset against the current index, or set "
        f"eval_stale_label_policy to {STALE_POLICY_UNSCORABLE!r} to score the "
        "remaining items and report these separately."
    )


def stale_label_policy(config: Any) -> str:
    """The configured policy, falling back to fail-fast on an unknown value.

    An unrecognised setting must not quietly become the permissive branch:
    that would turn a typo into silently-scored stale labels, which is the
    exact failure this module exists to prevent.
    """
    configured = str(getattr(config, "eval_stale_label_policy", STALE_POLICY_FAIL) or "")
    return configured if configured in STALE_POLICIES else STALE_POLICY_FAIL


def partition_eligible(
    response: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split a search response into what the app would use and what it refused.

    Mirrors the policy gate in ``ConversationGraph._normalize_chunks``
    without its Prometheus side effects — see the module docstring. Handles
    both the flat and the Qdrant-nested payload shapes, as that method does.

    The refusals are returned rather than discarded because they are the
    difference between "the golden chunk was never retrieved" and "it was
    retrieved and then barred", which are opposite bugs with the same
    Recall@10.
    """
    eligible: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for item in response.get("chunks") or response.get("results") or []:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") or {}
        metadata = item.get("metadata") or payload.get("metadata") or {}
        review_status = (
            item.get("review_status")
            or payload.get("review_status")
            or metadata.get("review_status")
            or "clean"
        )
        allowed = bool(
            item.get(
                "retrieval_allowed",
                payload.get("retrieval_allowed", metadata.get("retrieval_allowed", True)),
            )
        )
        if not allowed:
            dropped.append(dropped_view(item, DROP_RETRIEVAL_NOT_ALLOWED))
            continue
        if review_status == "removed":
            dropped.append(dropped_view(item, DROP_REVIEW_REMOVED))
            continue
        eligible.append({**metadata, **payload, **item})
    return eligible, dropped


def eligible_chunks(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieved chunks the application would have been willing to use."""
    return partition_eligible(response)[0]


def retrieved_ids(chunks: List[Dict[str, Any]], match_mode: str) -> List[str]:
    """Extract the ranked ids to score, in retrieval order."""
    field = "chunk_id" if match_mode == MATCH_CHUNK else "file_id"
    ids: List[str] = []
    for chunk in chunks:
        value = chunk.get(field) or (chunk.get("document_id") if field == "file_id" else None)
        if value:
            ids.append(str(value))
    return ids


def candidate_depth(config: Any) -> int:
    """How many candidates one retrieval eval item must ask for.

    Retrieval eval does **not** use ``top_k_documents``. That setting sizes
    the context an answer is generated from — six chunks by default — and a
    run scoring Recall@20 over six candidates reports the Recall@6 number
    under a wider name. Every k in :data:`K_VALUES` must be observable, so
    the depth is floored at ``max(K_VALUES)`` even if ``eval_candidate_k`` is
    configured lower: the alternative is a metric that silently cannot reach
    its own denominator.

    Nothing here clamps the metrics themselves. If the vector store returns
    fewer candidates than requested, Recall@20 is still computed against the
    full ground truth and reads low, which is the honest answer.
    """
    configured = getattr(config, "eval_candidate_k", 0) or 0
    return max(int(configured), max(K_VALUES))


class EvalRunner:
    """Run datasets against live retrieval and persist scored results."""

    def __init__(
        self,
        config: RAGConfig,
        store: EvalStore,
        backend_client: Any,
        logger: Any = None,
        graph_runner: Any = None,
    ) -> None:
        self.config = config
        self.store = store
        self.backend_client = backend_client
        self.logger = logger
        # Only `end_to_end` needs it. When absent, that mode is refused with a
        # reason rather than silently downgraded to a retrieval run whose
        # answer-quality columns would all be blank.
        self.graph_runner = graph_runner
        # Strong references to in-flight runs. asyncio only holds a weak
        # reference to a task, so without this set a run can be garbage
        # collected mid-execution and silently never finish.
        self._tasks: Set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def handle(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one eval RPC action.

        Args:
            action: One of :data:`EVAL_ACTIONS`.
            payload: The RPC business payload.

        Returns:
            The reply body, or a dict carrying ``error`` — which
            ``build_reply_envelope`` turns into an unsuccessful reply.
        """
        try:
            if action == LIST_EVAL_DATASETS:
                return {"datasets": self.store.list_datasets()}
            if action == CREATE_EVAL_DATASET:
                if "content" in payload:
                    prepared = await self._prepare_import(
                        payload.get("content"),
                        str(payload.get("format") or ""),
                    )
                    if prepared["preparation"]["blocking"]:
                        first = prepared["validation"]["errors"][0]
                        code = first.get("code")
                        raise EvalValidationError(
                            f"{f'{code}: ' if code else ''}{first.get('message')}"
                        )
                    return {
                        "dataset": self.store.create_dataset(
                            payload.get("name") or "",
                            payload.get("description"),
                            prepared["items"],
                        ),
                        "preparation": prepared["preparation"],
                    }
                return {
                    "dataset": self.store.create_dataset(
                        payload.get("name") or "",
                        payload.get("description"),
                        payload.get("items"),
                    )
                }
            if action == VALIDATE_EVAL_DATASET:
                prepared = await self._prepare_import(
                    payload.get("content"),
                    str(payload.get("format") or ""),
                )
                return {
                    "validation": prepared["validation"],
                    "preparation": prepared["preparation"],
                }
            if action == UPDATE_EVAL_DATASET:
                return {
                    "dataset": self.store.update_dataset(
                        str(payload.get("dataset_id") or ""),
                        name=payload.get("name"),
                        description=payload.get("description"),
                        items=payload.get("items"),
                    )
                }
            if action == DELETE_EVAL_DATASET:
                return self.store.delete_dataset(str(payload.get("dataset_id") or ""))
            if action == START_EVAL_RUN:
                return {
                    "run": await self.start_run(
                        str(payload.get("dataset_id") or ""),
                        str(payload.get("mode") or MODE_RETRIEVAL),
                        payload.get("pipeline_mode") or None,
                    )
                }
            if action == LIST_EVAL_RUNS:
                return {
                    "runs": self.store.list_runs(
                        payload.get("dataset_id"), payload.get("limit") or 0
                    )
                }
            if action == GET_EVAL_RUN:
                return {"run": self.store.get_run(str(payload.get("run_id") or ""))}
            return error_reply(ERROR_VALIDATION, f"Unsupported eval action: {action!r}")
        except EvalValidationError as exc:
            return error_reply(ERROR_VALIDATION, str(exc))
        except EvalNotFound as exc:
            return error_reply(ERROR_NOT_FOUND, str(exc))
        except EvalAccessDenied as exc:
            return error_reply(ERROR_FORBIDDEN, str(exc))

    async def _prepare_import(self, content: Any, source_format: str) -> Dict[str, Any]:
        """Parse, resolve tenant-scoped filenames, and report import readiness."""
        validation = self.store.validate_import(content, source_format)
        if not validation.get("valid"):
            return {
                "items": [],
                "validation": validation,
                "preparation": {
                    "ready": 0,
                    "unresolved": 0,
                    "ambiguous": 0,
                    "unanswerable": 0,
                    "blocking": True,
                },
            }

        items = self.store.parse_import(content, source_format)
        labels = list(
            dict.fromkeys(
                label
                for item in items
                if item.get("answerable") is not False
                for label in item.get("expected_file_names") or []
            )
        )
        resolutions: List[Dict[str, Any]] = []
        if labels:
            identity = identity_from_context(required=True)
            request = ConversationRequest(
                user_message="",
                mode="regular",
                tenant_id=identity.tenant_id,
                user_id=identity.user_id,
                role=identity.role,
                admin_id=identity.admin_id,
            )
            reply = await self.backend_client.resolve_file_labels(request, labels)
            resolutions = reply.get("resolutions") or []

        file_result = prepare_file_labels(items, resolutions)
        prepared_items = file_result["items"]
        identity = identity_from_context(required=True)
        request = ConversationRequest(
            user_message="",
            mode="regular",
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            role=identity.role,
            admin_id=identity.admin_id,
        )
        chunk_requests = [
            {
                "item_id": str(item.get("item_id") or ""),
                "file_ids": list(item.get("relevant_file_ids") or []),
                "facts": list(item.get("expected_claims") or []),
            }
            for item in prepared_items
            if item.get("answerable") is not False and item.get("relevant_file_ids")
        ]
        chunk_resolutions: List[Dict[str, Any]] = []
        if chunk_requests:
            reply = await self.backend_client.resolve_chunk_labels(request, chunk_requests)
            chunk_resolutions = reply.get("resolutions") or []
        chunk_result = prepare_chunk_labels(prepared_items, chunk_resolutions)
        counts = file_result["counts"]
        blocking = file_result["blocking"] or chunk_result["blocking"]
        validation = {
            **validation,
            "valid": not blocking,
            "valid_items": max(
                0,
                counts["ready"]
                + counts["unanswerable"]
                - chunk_result["counts"]["unready_items"],
            ),
            "invalid_items": (
                counts["unresolved"]
                + counts["ambiguous"]
                + chunk_result["counts"]["unready_items"]
            ),
            "errors": [
                *validation.get("errors", []),
                *file_result["errors"],
                *chunk_result["errors"],
            ],
            "warnings": chunk_result["warnings"],
        }
        return {
            "items": chunk_result["items"],
            "validation": validation,
            "preparation": {
                **counts,
                **chunk_result["counts"],
                "blocking": blocking,
                "warnings": chunk_result["warnings"],
            },
        }

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    async def start_run(
        self,
        dataset_id: str,
        mode: str = MODE_RETRIEVAL,
        pipeline_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Open a run and execute it in the background.

        Returns as soon as the run document exists, carrying its ``run_id``.
        A synchronous RPC would blow the gateway's timeout on any dataset
        worth having, so the caller polls ``get_eval_run`` instead.

        Args:
            dataset_id: The dataset to execute.
            mode: ``retrieval`` (default, LLM-free) or ``end_to_end``.
            pipeline_mode: ``regular``, ``extended``, or ``None`` to let the
                run's evaluation mode decide.

        Raises:
            EvalValidationError: On an unknown mode, or on ``end_to_end``
                with no graph available to run.
        """
        prepared = await self.open_run(dataset_id, mode, pipeline_mode)
        task = asyncio.create_task(prepared.execute())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return prepared.run

    async def open_run(
        self,
        dataset_id: str,
        mode: str = MODE_RETRIEVAL,
        pipeline_mode: Optional[str] = None,
        benchmark_id: Optional[str] = None,
    ) -> "PreparedRun":
        """Validate and open a run document without executing it.

        Split out of :meth:`start_run` so that a caller which needs to know
        when the run finished — the benchmark orchestrator, which must not
        start an expensive phase until the cheap one has reported — can await
        it directly instead of polling the store it just wrote to.

        Args:
            dataset_id: The dataset to execute.
            mode: ``retrieval`` (default, LLM-free) or ``end_to_end``.
            pipeline_mode: Which conversation pipeline to drive. ``None``
                defaults to :data:`PIPELINE_REGULAR` for an ``end_to_end``
                run and stays ``None`` for a ``retrieval`` one, which drives
                no pipeline.

        Raises:
            EvalValidationError: On an unknown evaluation or pipeline mode,
                on ``end_to_end`` with no graph available to run, or on a
                pipeline mode asked of a ``retrieval`` run, whose single
                ``search_chunks`` call the pipeline cannot influence.
            benchmark_id: The benchmark this run is a phase of, recorded on
                the run document. ``None`` for a run started on its own.
        """
        if mode not in EVAL_MODES:
            raise EvalValidationError(f"Unsupported eval run mode: {mode!r}")
        if mode == MODE_END_TO_END and self.graph_runner is None:
            raise EvalValidationError(
                "end_to_end runs are unavailable: no conversation graph is wired"
            )
        if pipeline_mode is not None and pipeline_mode not in PIPELINE_MODES:
            raise EvalValidationError(f"Unsupported pipeline mode: {pipeline_mode!r}")
        if pipeline_mode is not None and mode != MODE_END_TO_END:
            # Refused rather than ignored. A retrieval run's ranking comes
            # from one `search_chunks` call that the conversation pipeline
            # never touches, so accepting the argument would let two runs
            # record different pipelines while having executed identically.
            raise EvalValidationError(
                "pipeline_mode applies to end_to_end runs only: a retrieval "
                "run issues one pipeline-independent search"
            )
        if mode == MODE_END_TO_END:
            pipeline_mode = pipeline_mode or PIPELINE_REGULAR
        # Raises EvalAccessDenied / EvalNotFound before anything is written,
        # so a refused request leaves no run document behind.
        dataset = self.store.get_dataset(dataset_id)
        identity = identity_from_context(required=True)
        items = dataset.get("items") or []
        if not items:
            raise EvalValidationError("Dataset has no items to evaluate")
        unresolved = [
            str(item.get("item_id") or index)
            for index, item in enumerate(items)
            if item.get("expected_file_names")
            and not item.get("relevant_chunk_ids")
            and not item.get("relevant_file_ids")
        ]
        if unresolved:
            raise EvalValidationError(
                "Dataset has unresolved expected_file_names; resolve filenames "
                f"before running it (items: {', '.join(unresolved[:10])})"
            )

        match_mode = dataset_match_mode(items)
        run = self.store.create_run(
            dataset_id,
            build_config_snapshot(
                self.config,
                mode=mode,
                # What this run's ranking was actually drawn from. An
                # `end_to_end` run is scored over the graph's own sources, so
                # its depth is the production one — recording the eval depth
                # there would claim a candidate pool the run never saw.
                candidate_k=(
                    self.config.top_k_documents
                    if mode == MODE_END_TO_END
                    else candidate_depth(self.config)
                ),
                pipeline_mode=pipeline_mode,
            ),
            match_mode,
            mode=mode,
            pipeline_mode=pipeline_mode,
            benchmark_id=benchmark_id,
            # Snapshot, not a reference: the dataset can be edited between
            # this run and the next time anybody reads it, and a run that
            # re-reported its dataset's *current* labels would quietly
            # rewrite its own provenance.
            dataset_version=dataset.get("dataset_version"),
            dataset_sha256=dataset.get("dataset_sha256"),
        )

        return PreparedRun(
            run=run,
            runner=self,
            identity=identity,
            items=items,
            match_mode=match_mode,
            mode=mode,
            pipeline_mode=pipeline_mode,
        )

    async def execute_run(
        self,
        run_id: str,
        identity: AuthIdentity,
        items: List[Dict[str, Any]],
        match_mode: str,
        mode: str = MODE_RETRIEVAL,
        pipeline_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Score every item, then close the run.

        The identity is re-bound explicitly rather than left to task context
        inheritance: every downstream RPC signs itself from the context, so a
        run whose context was lost would fail on its first embed call with an
        authentication error rather than an obvious one.

        Wrapped so that **no exception can leave the run in ``running``** —
        that state is indistinguishable from a run still in progress, which
        is what makes a stuck eval dashboard useless.

        Returns:
            How the run closed: ``run_id``, terminal ``status``, aggregated
            ``results`` and ``error``. The same facts the store now holds,
            handed back so an orchestrator awaiting the run does not have to
            read back the document it just caused to be written.
        """
        tenant_id = identity.tenant_id
        # The same bound as retrieval mode, deliberately not raised for
        # end_to_end: that mode is heavier per item, not more entitled to
        # concurrency, and it shares the live LLM the application is serving.
        semaphore = asyncio.Semaphore(max(1, self.config.eval_run_concurrency))
        try:
            # This is a server-controlled classification. It is deliberately
            # absent from the public eval request contract.
            with bound_context(**identity.to_dict(), traffic_class="eval"):
                # Before anything is retrieved: a run that scores against
                # labels the index cannot return is not measuring retrieval.
                report = await self._validate_labels(identity, items, match_mode)
                self.store.record_label_validation(run_id, tenant_id, report.summary)
                if report.blocking:
                    error = stale_label_error(report.summary)
                    self.store.finish_run(
                        run_id,
                        tenant_id,
                        status=RUN_FAILED,
                        error=error,
                    )
                    return _run_summary(run_id, RUN_FAILED, {}, error)
                rows = await asyncio.gather(
                    *(
                        self._score_item(
                            run_id,
                            identity,
                            item,
                            match_mode,
                            semaphore,
                            mode,
                            unscorable=str(item.get("item_id") or "") in report.unscorable,
                            pipeline_mode=pipeline_mode,
                        )
                        for item in items
                    )
                )
            failed = _all_failed(rows)
            status = RUN_FAILED if failed else RUN_COMPLETED
            results = aggregate(rows, mode)
            error = _first_error(rows) if failed else None
            self.store.finish_run(
                run_id,
                tenant_id,
                status=status,
                results=results,
                error=error,
            )
            return _run_summary(run_id, status, results, error)
        except asyncio.CancelledError:
            # A cancelled run is still a closed run. Left in `running` it
            # would look like work still in flight after the loop that was
            # doing it is gone.
            self.store.finish_run(
                run_id,
                tenant_id,
                status=RUN_FAILED,
                error="Eval run was cancelled before it finished",
            )
            raise
        except Exception as exc:  # noqa: BLE001 - the run must always close
            self._log("eval_runner:execute", "Eval run failed", {"error": str(exc)})
            self.store.finish_run(run_id, tenant_id, status=RUN_FAILED, error=str(exc))
            return _run_summary(run_id, RUN_FAILED, {}, str(exc))

    async def _validate_labels(
        self,
        identity: AuthIdentity,
        items: List[Dict[str, Any]],
        match_mode: str,
    ) -> LabelReport:
        """Check the dataset's labels against the live index.

        One RPC for the whole dataset, before the first embed call, so the
        cost is a single round trip however large the golden set is.

        **A check that could not be made is a warning, not a failure.** If
        vector_db is unreachable or does not know the action, the run
        proceeds and records ``checked: False`` with the reason, and the
        panel says the labels were not verified. Failing instead would make
        every eval run depend on a newly deployed action, and an eval harness
        that cannot run is not safer than one that says what it did not
        check.
        """
        policy = stale_label_policy(self.config)
        if not getattr(self.config, "eval_validate_labels", True):
            return _unchecked_report(NOT_CHECKED_DISABLED, policy)

        chunk_ids, file_ids = label_targets(items, match_mode)
        if not chunk_ids and not file_ids:
            return _unchecked_report(NOT_CHECKED_NO_LABELS, policy)

        request = ConversationRequest(
            user_message="",
            mode="regular",
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            role=identity.role,
            admin_id=identity.admin_id,
        )
        try:
            verified = await self.backend_client.verify_label_ids(
                request,
                sorted(chunk_ids),
                sorted(file_ids),
            )
        except Exception as exc:  # noqa: BLE001 - an unchecked run, not a failed one
            self._log(
                "eval_runner:validate_labels",
                "Golden-set labels could not be verified",
                {"error": str(exc)},
            )
            return _unchecked_report(NOT_CHECKED_UNAVAILABLE, policy, str(exc))

        return classify_labels(
            items,
            match_mode,
            verified,
            policy=policy,
            max_reported_ids=int(getattr(self.config, "eval_max_reported_stale_ids", 50)),
        )

    async def _score_item(
        self,
        run_id: str,
        identity: AuthIdentity,
        item: Dict[str, Any],
        match_mode: str,
        semaphore: asyncio.Semaphore,
        mode: str = MODE_RETRIEVAL,
        *,
        unscorable: bool = False,
        pipeline_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve for one item, score it, and persist the row.

        The semaphore is held across the whole retrieval, not just its start:
        an unbounded fan-out over a large dataset would bury the embedding
        service, which is serving live traffic from the same instance.

        A failed item is recorded and does not abort the run — one bad query
        should not discard the other 199 results.

        An ``unscorable`` item is not retrieved at all. Its ground truth
        names ids the index cannot return, so every metric over it would be
        a measurement of the labels rather than of retrieval — and spending
        an embed call to produce one would be paying for a wrong number.

        Every retrieved item carries a bounded ``retrieval_trace``: the
        candidate lineage that explains its score. A failed item keeps
        whatever lineage it reached before the failure — the step it died on
        is the most useful thing it can still report.
        """
        tenant_id = identity.tenant_id
        query = str(item.get("query") or "")
        item_mode = item_match_mode(item, match_mode)
        relevant = relevant_ids(item, match_mode)
        row: Dict[str, Any] = {
            "item_id": item.get("item_id"),
            "query": query,
            "match_mode": item_mode,
            "expected_ids": sorted(relevant),
            "retrieved_ids": [],
            "first_hit_rank": None,
            "reciprocal_rank": None,
            "recall_at_10": None,
            "latency_ms": None,
            "skipped": not relevant,
            # Distinct from `skipped`, which means "this item was never
            # labelled". An unscorable item *is* labelled — against chunks
            # the live index no longer offers.
            "unscorable": unscorable,
            "error": None,
            "outcome": "success",
            "guardrail_stage": None,
        }
        if unscorable:
            row["failure_attribution"] = classify_item(row)
            self.store.append_item_result(run_id, tenant_id, row)
            return row

        trace = RetrievalTrace.from_config(self.config)
        started = time.monotonic()
        try:
            async with semaphore:
                request = ConversationRequest(
                    user_message=query,
                    # The pipeline the run declared. A retrieval run passes
                    # None and falls back to `regular`, which its single
                    # `search_chunks` call does not read — the field is only
                    # load-bearing once the graph is what executes the item.
                    mode=pipeline_mode or PIPELINE_REGULAR,
                    tenant_id=tenant_id,
                    user_id=identity.user_id,
                    role=identity.role,
                    admin_id=identity.admin_id,
                )
                if mode == MODE_END_TO_END:
                    ids = await self._run_graph_item(request, row, item_mode, trace)
                else:
                    depth = candidate_depth(self.config)
                    response = await self.backend_client.search_chunks(
                        request,
                        query,
                        {},
                        "eval",
                        top_k=depth,
                    )
                    eligible, dropped = partition_eligible(response)
                    # A retrieval run is one search, so its lineage is one
                    # stage and the context is that stage after the
                    # eligibility gate. Both are recorded: the pair is what
                    # distinguishes a chunk that was never a candidate from
                    # one the gate refused.
                    trace.record_stage(
                        STAGE_BASE,
                        eligible,
                        query=query,
                        query_source="dataset_query",
                        requested_k=depth,
                        returned_count=len(
                            response.get("chunks") or response.get("results") or []
                        ),
                        dropped=dropped,
                    )
                    trace.record_stage(STAGE_FINAL_CONTEXT, eligible)
                    ids = retrieved_ids(eligible, item_mode)
        except Exception as exc:  # noqa: BLE001 - one item, not the run
            row["error"] = str(exc)
            row["outcome"] = "failed"
            row["latency_ms"] = (time.monotonic() - started) * 1000
            row["retrieval_trace"] = trace.to_payload()
            row["failure_attribution"] = classify_item(row)
            self.store.append_item_result(run_id, tenant_id, row)
            return row

        row["latency_ms"] = (time.monotonic() - started) * 1000
        row["retrieval_trace"] = trace.to_payload()
        row["retrieved_ids"] = ids[:MAX_ROW_IDS]
        if row["outcome"] == "guardrail_blocked":
            row["failure_attribution"] = classify_item(row)
            self.store.append_item_result(run_id, tenant_id, row)
            return row
        if relevant:
            deduped = retrieval_metrics.dedupe(ids)
            row["first_hit_rank"] = next(
                (index for index, value in enumerate(deduped, 1) if value in relevant),
                None,
            )
            row["reciprocal_rank"] = retrieval_metrics.reciprocal_rank(ids, relevant)
            row["recall_at_10"] = retrieval_metrics.recall_at_k(ids, relevant, 10)
            row["scores"] = _item_scores(ids, relevant)

        # Attributed here, from the row and the lineage that produced it,
        # rather than recomputed at aggregation time: the row is what the
        # drill-down renders, and a category derived twice from two different
        # inputs is a category that can disagree with itself.
        row["failure_attribution"] = classify_item(row)
        self.store.append_item_result(run_id, tenant_id, row)
        return row

    async def _run_graph_item(
        self,
        request: ConversationRequest,
        row: Dict[str, Any],
        item_mode: str,
        trace: RetrievalTrace,
    ) -> List[str]:
        """Run the full graph for one item and record its answer quality.

        Turn-metric recording is off: these are synthetic turns, and letting
        them into `metrics_turn_facts` would shift the tenant averages the
        run exists to measure.

        Returns:
            The retrieved ids, so the caller scores retrieval exactly as it
            does in retrieval mode — an `end_to_end` run reports both.
        """
        emitter = CollectingConversationEmitter(request)
        # The graph fills the trace as it retrieves: an end_to_end item's
        # lineage is the pipeline's own passes, not a reconstruction.
        result = await self.graph_runner.run(
            request,
            emitter,
            record_metrics=False,
            retrieval_trace=trace,
        )
        review = result.get("review") or {}
        citations = result.get("citation_metrics") or {}
        row["answer"] = result.get("answer", "")
        row["groundedness"] = review.get("groundedness_score")
        row["hallucination_verdict"] = review.get("hallucination_verdict")
        row["unsupported_claim_count"] = review.get("unsupported_claim_count")
        row["citation_precision"] = citations.get("citation_precision")
        row["citation_recall"] = citations.get("citation_recall")
        row["citation_count"] = citations.get("citation_count")
        row["outcome"] = result.get("outcome", "success")
        row["guardrail_stage"] = result.get("guardrail_stage")
        return retrieved_ids(eligible_chunks({"chunks": result.get("sources") or []}), item_mode)

    def _log(self, event: str, message: str, data: Dict[str, Any]) -> None:
        if self.logger is not None:
            self.logger.log(event, message, data)


@dataclass
class PreparedRun:
    """A validated, persisted run that has not started executing yet.

    Everything that can be refused — an unknown mode, a missing graph, an
    unresolved dataset — has already been refused by the time one of these
    exists, and the run document is already in the store. What is left is the
    work, which :meth:`execute` performs and awaits.

    This is what lets the benchmark orchestrator run phases in order: it
    needs the ``run_id`` immediately, to record which run a phase became, and
    it needs to know when that run finished, to decide whether the next phase
    should start at all.
    """

    run: Dict[str, Any]
    runner: "EvalRunner"
    identity: AuthIdentity
    items: List[Dict[str, Any]]
    match_mode: str
    mode: str = MODE_RETRIEVAL
    pipeline_mode: Optional[str] = None

    @property
    def run_id(self) -> str:
        """The opened run's id."""
        return str(self.run.get("run_id") or "")

    async def execute(self) -> Dict[str, Any]:
        """Execute the run to completion and return how it closed."""
        return await self.runner.execute_run(
            self.run_id,
            self.identity,
            self.items,
            self.match_mode,
            self.mode,
            self.pipeline_mode,
        )


def _run_summary(
    run_id: str,
    status: str,
    results: Dict[str, Any],
    error: Optional[str],
) -> Dict[str, Any]:
    """How one run closed, for a caller that awaited it."""
    return {
        "run_id": run_id,
        "status": status,
        "results": results or {},
        "error": error,
    }


def _item_scores(ids: List[str], relevant: Set[str]) -> Dict[str, Dict[str, float]]:
    """Every metric at every k for one item, keyed by str(k) for Mongo."""
    return {
        "recall_at_k": {
            str(k): retrieval_metrics.recall_at_k(ids, relevant, k) for k in K_VALUES
        },
        "precision_at_k": {
            str(k): retrieval_metrics.precision_at_k(ids, relevant, k) for k in K_VALUES
        },
        "hit_rate_at_k": {
            str(k): retrieval_metrics.hit_rate_at_k(ids, relevant, k) for k in K_VALUES
        },
        "ndcg_at_k": {
            str(k): retrieval_metrics.ndcg_at_k(ids, relevant, k) for k in K_VALUES
        },
    }


def aggregate(rows: List[Dict[str, Any]], mode: str = MODE_RETRIEVAL) -> Dict[str, Any]:
    """Average the per-item scores into the run's ``results``.

    Unlabelled, unscorable and failed items are **excluded from every mean**,
    not counted as zeros, and each count is reported alongside. A
    half-labelled dataset should be visible as a small denominator, never as
    a retrieval regression — and neither should a dataset whose labels the
    index no longer holds.

    An ``end_to_end`` run adds answer-quality figures under
    ``answer_quality``, each with the count of items it was measured over —
    an item whose judge failed, or whose answer cited nothing, contributes
    nothing rather than a zero.

    ``failure_attribution`` counts each item's stage category from
    :mod:`app.services.failure_attribution`, reusing the verdict already
    stored on the row so the summary and the drill-down cannot disagree.
    """
    scored = [row for row in rows if row.get("scores")]
    skipped = sum(1 for row in rows if row.get("skipped"))
    unscorable = sum(1 for row in rows if row.get("unscorable"))
    blocked = sum(1 for row in rows if row.get("outcome") == "guardrail_blocked")
    failed = sum(
        1 for row in rows
        if row.get("outcome", "failed" if row.get("error") else "success") == "failed"
    )
    latencies = [
        row["latency_ms"] for row in rows if isinstance(row.get("latency_ms"), (int, float))
    ]

    def mean_at_k(metric: str) -> Dict[str, Optional[float]]:
        return {
            str(k): _mean([row["scores"][metric][str(k)] for row in scored])
            for k in K_VALUES
        }

    return {
        "recall_at_k": mean_at_k("recall_at_k"),
        "precision_at_k": mean_at_k("precision_at_k"),
        "hit_rate_at_k": mean_at_k("hit_rate_at_k"),
        "ndcg_at_k": mean_at_k("ndcg_at_k"),
        "mrr": _mean([row.get("reciprocal_rank") for row in scored]),
        "items_evaluated": len(scored),
        "items_skipped": skipped,
        "items_unscorable": unscorable,
        "items_guardrail_blocked": blocked,
        "items_failed": failed,
        "mean_latency_ms": _mean(latencies),
        # Where the failures were, not just how many. Reported for every run
        # and every benchmark phase — a phase stores exactly this dict — so
        # the stage that lost an item is visible without opening its trace.
        "failure_attribution": aggregate_attribution(rows),
        **({"answer_quality": _answer_quality(rows)} if mode == MODE_END_TO_END else {}),
    }


def _answer_quality(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Answer-quality means for an ``end_to_end`` run, with denominators.

    The hallucination rate divides by the items that actually got a verdict,
    not by the dataset size: an item whose judge failed is unmeasured, and
    counting it as "not hallucinating" would flatter every run in which the
    judge was flaky.
    """
    rows = [row for row in rows if row.get("outcome") != "guardrail_blocked"]
    verdicts = [row.get("hallucination_verdict") for row in rows]
    judged = [verdict for verdict in verdicts if verdict is not None]
    hallucinating = sum(1 for verdict in judged if verdict != "none")
    severe = sum(1 for verdict in judged if verdict == "severe")
    return {
        "groundedness": aggregate_mean([row.get("groundedness") for row in rows]),
        "citation_precision": aggregate_mean(
            [row.get("citation_precision") for row in rows]
        ),
        "citation_recall": aggregate_mean([row.get("citation_recall") for row in rows]),
        "unsupported_claims": aggregate_mean(
            [row.get("unsupported_claim_count") for row in rows]
        ),
        "hallucination_rate": (hallucinating / len(judged)) if judged else None,
        "hallucination_severe_rate": (severe / len(judged)) if judged else None,
        "items_judged": len(judged),
        "items_unjudged": len(rows) - len(judged),
    }


def _mean(values: List[Any]) -> Optional[float]:
    """Mean of the present values, or None when there are none.

    None rather than 0.0: a mean over nothing is unknown, and a confident
    "Recall@5: 0%" over an empty run is the wrong thing to put on a chart.
    """
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _all_failed(rows: List[Dict[str, Any]]) -> bool:
    """Whether every item errored — a systemic failure, not a bad query."""
    return bool(rows) and all(row.get("error") for row in rows)


def _first_error(rows: List[Dict[str, Any]]) -> Optional[str]:
    """The first recorded item error, used as the run's failure message."""
    return next((row["error"] for row in rows if row.get("error")), None)


def create_eval_runner(
    config: RAGConfig,
    store: EvalStore,
    backend_client: Any,
    logger: Any = None,
    graph_runner: Any = None,
) -> EvalRunner:
    """Create the eval runner.

    ``graph_runner`` is required only for ``end_to_end`` runs; without it
    that mode is refused rather than downgraded.
    """
    return EvalRunner(config, store, backend_client, logger, graph_runner)
