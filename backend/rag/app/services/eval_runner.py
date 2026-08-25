"""Execute a golden-set dataset against live retrieval and score it.

**Retrieval only. This module never calls the LLM.** No generation, no answer
evaluation, no reranker-free shortcut. That is what makes a 200-query run
finish in seconds and cost nothing, which in turn is what makes it usable as
a regression gate somebody actually runs before merging. Answer-quality
evaluation is phase 6's problem.

Retrieval goes through ``ConversationBackendClient.search_chunks`` — the same
call the conversation graph makes — because the number is only meaningful if
it measures the retrieval the application actually performs. Queries are
tagged ``pass_name="eval"`` so downstream services can tell an eval sweep from
live traffic in their own logs.

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
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.config import RAGConfig
from app.services import retrieval_metrics
from app.services.conversation_types import ConversationRequest
from app.services.eval_store import (
    RUN_COMPLETED,
    RUN_FAILED,
    EvalAccessDenied,
    EvalNotFound,
    EvalStore,
    EvalValidationError,
    build_config_snapshot,
)
from shared.auth import AuthIdentity, identity_from_context
from shared.context import bound_context

# The k values every run reports. Deliberately not configurable: they are
# part of the stored `results` shape, and two runs carrying different k sets
# under the same field names would be silently incomparable.
K_VALUES: Tuple[int, ...] = (1, 3, 5, 10, 20)

MATCH_CHUNK = "chunk_id"
MATCH_FILE = "file_id"
MATCH_MIXED = "mixed"

# How many retrieved ids one per-item row keeps for the drill-down. The full
# list is bounded by top_k anyway; this is a guard against a future config
# that raises it, not a meaningful truncation today.
MAX_ROW_IDS = 20

# Action strings, mirroring `RagAction` in the gateway's core/constants.py.
# The rag service cannot import gateway code, so they are defined once here
# and the two must stay in step — the same arrangement as METRICS_ACTION.
LIST_EVAL_DATASETS = "list_eval_datasets"
CREATE_EVAL_DATASET = "create_eval_dataset"
UPDATE_EVAL_DATASET = "update_eval_dataset"
DELETE_EVAL_DATASET = "delete_eval_dataset"
START_EVAL_RUN = "start_eval_run"
LIST_EVAL_RUNS = "list_eval_runs"
GET_EVAL_RUN = "get_eval_run"

EVAL_ACTIONS = frozenset(
    {
        LIST_EVAL_DATASETS,
        CREATE_EVAL_DATASET,
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


def _error_reply(kind: str, message: str) -> Dict[str, Any]:
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


def eligible_chunks(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieved chunks the application would have been willing to use.

    Mirrors the policy gate in ``ConversationGraph._normalize_chunks``
    without its Prometheus side effects — see the module docstring. Handles
    both the flat and the Qdrant-nested payload shapes, as that method does.
    """
    eligible: List[Dict[str, Any]] = []
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
        if not allowed or review_status == "removed":
            continue
        eligible.append({**metadata, **payload, **item})
    return eligible


def retrieved_ids(chunks: List[Dict[str, Any]], match_mode: str) -> List[str]:
    """Extract the ranked ids to score, in retrieval order."""
    field = "chunk_id" if match_mode == MATCH_CHUNK else "file_id"
    ids: List[str] = []
    for chunk in chunks:
        value = chunk.get(field) or (chunk.get("document_id") if field == "file_id" else None)
        if value:
            ids.append(str(value))
    return ids


class EvalRunner:
    """Run datasets against live retrieval and persist scored results."""

    def __init__(
        self,
        config: RAGConfig,
        store: EvalStore,
        backend_client: Any,
        logger: Any = None,
    ) -> None:
        self.config = config
        self.store = store
        self.backend_client = backend_client
        self.logger = logger
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
                return {
                    "dataset": self.store.create_dataset(
                        payload.get("name") or "",
                        payload.get("description"),
                        payload.get("items"),
                    )
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
                return {"run": await self.start_run(str(payload.get("dataset_id") or ""))}
            if action == LIST_EVAL_RUNS:
                return {
                    "runs": self.store.list_runs(
                        payload.get("dataset_id"), payload.get("limit") or 0
                    )
                }
            if action == GET_EVAL_RUN:
                return {"run": self.store.get_run(str(payload.get("run_id") or ""))}
            return _error_reply(ERROR_VALIDATION, f"Unsupported eval action: {action!r}")
        except EvalValidationError as exc:
            return _error_reply(ERROR_VALIDATION, str(exc))
        except EvalNotFound as exc:
            return _error_reply(ERROR_NOT_FOUND, str(exc))
        except EvalAccessDenied as exc:
            return _error_reply(ERROR_FORBIDDEN, str(exc))

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    async def start_run(self, dataset_id: str) -> Dict[str, Any]:
        """Open a run and execute it in the background.

        Returns as soon as the run document exists, carrying its ``run_id``.
        A synchronous RPC would blow the gateway's timeout on any dataset
        worth having, so the caller polls ``get_eval_run`` instead.
        """
        # Raises EvalAccessDenied / EvalNotFound before anything is written,
        # so a refused request leaves no run document behind.
        dataset = self.store.get_dataset(dataset_id)
        identity = identity_from_context(required=True)
        items = dataset.get("items") or []
        if not items:
            raise EvalValidationError("Dataset has no items to evaluate")

        match_mode = dataset_match_mode(items)
        run = self.store.create_run(
            dataset_id, build_config_snapshot(self.config), match_mode
        )

        task = asyncio.create_task(
            self._execute(run["run_id"], identity, items, match_mode)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    async def _execute(
        self,
        run_id: str,
        identity: AuthIdentity,
        items: List[Dict[str, Any]],
        match_mode: str,
    ) -> None:
        """Score every item, then close the run.

        The identity is re-bound explicitly rather than left to task context
        inheritance: every downstream RPC signs itself from the context, so a
        run whose context was lost would fail on its first embed call with an
        authentication error rather than an obvious one.

        Wrapped so that **no exception can leave the run in ``running``** —
        that state is indistinguishable from a run still in progress, which
        is what makes a stuck eval dashboard useless.
        """
        tenant_id = identity.tenant_id
        semaphore = asyncio.Semaphore(max(1, self.config.eval_run_concurrency))
        try:
            with bound_context(**identity.to_dict()):
                rows = await asyncio.gather(
                    *(
                        self._score_item(run_id, identity, item, match_mode, semaphore)
                        for item in items
                    )
                )
            failed = _all_failed(rows)
            self.store.finish_run(
                run_id,
                tenant_id,
                status=RUN_FAILED if failed else RUN_COMPLETED,
                results=aggregate(rows),
                error=_first_error(rows) if failed else None,
            )
        except Exception as exc:  # noqa: BLE001 - the run must always close
            self._log("eval_runner:execute", "Eval run failed", {"error": str(exc)})
            self.store.finish_run(run_id, tenant_id, status=RUN_FAILED, error=str(exc))

    async def _score_item(
        self,
        run_id: str,
        identity: AuthIdentity,
        item: Dict[str, Any],
        match_mode: str,
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        """Retrieve for one item, score it, and persist the row.

        The semaphore is held across the whole retrieval, not just its start:
        an unbounded fan-out over a large dataset would bury the embedding
        service, which is serving live traffic from the same instance.

        A failed item is recorded and does not abort the run — one bad query
        should not discard the other 199 results.
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
            "error": None,
        }

        started = time.monotonic()
        try:
            async with semaphore:
                request = ConversationRequest(
                    user_message=query,
                    mode="regular",
                    tenant_id=tenant_id,
                    user_id=identity.user_id,
                    role=identity.role,
                    admin_id=identity.admin_id,
                )
                response = await self.backend_client.search_chunks(
                    request, query, {}, "eval"
                )
            ids = retrieved_ids(eligible_chunks(response), item_mode)
        except Exception as exc:  # noqa: BLE001 - one item, not the run
            row["error"] = str(exc)
            row["latency_ms"] = (time.monotonic() - started) * 1000
            self.store.append_item_result(run_id, tenant_id, row)
            return row

        row["latency_ms"] = (time.monotonic() - started) * 1000
        row["retrieved_ids"] = ids[:MAX_ROW_IDS]
        if relevant:
            deduped = retrieval_metrics.dedupe(ids)
            row["first_hit_rank"] = next(
                (index for index, value in enumerate(deduped, 1) if value in relevant),
                None,
            )
            row["reciprocal_rank"] = retrieval_metrics.reciprocal_rank(ids, relevant)
            row["recall_at_10"] = retrieval_metrics.recall_at_k(ids, relevant, 10)
            row["scores"] = _item_scores(ids, relevant)

        self.store.append_item_result(run_id, tenant_id, row)
        return row

    def _log(self, event: str, message: str, data: Dict[str, Any]) -> None:
        if self.logger is not None:
            self.logger.log(event, message, data)


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


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Average the per-item scores into the run's ``results``.

    Unlabelled and failed items are **excluded from every mean**, not counted
    as zeros, and both counts are reported alongside. A half-labelled dataset
    should be visible as a small denominator, never as a retrieval regression.
    """
    scored = [row for row in rows if row.get("scores")]
    skipped = sum(1 for row in rows if row.get("skipped"))
    failed = sum(1 for row in rows if row.get("error"))
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
        "items_failed": failed,
        "mean_latency_ms": _mean(latencies),
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
) -> EvalRunner:
    """Create the eval runner."""
    return EvalRunner(config, store, backend_client, logger)
