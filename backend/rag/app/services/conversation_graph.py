"""LangGraph-backed conversation orchestration for the `rag` service."""
from __future__ import annotations

import copy
import re
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.core.config import RAGConfig
from app.services.conversation_events import BaseConversationEmitter
from app.services.conversation_backend_client import ConversationBackendClient
from app.services.conversation_persistence import BaseConversationStore, make_json_safe
from app.services.conversation_tracing import ConversationTracer
from app.services.conversation_messages import (
    LLM_EVIDENCE_KEY,
    DownstreamRPCError,
    chunk_passages,
)
from app.services.citation_metrics import (
    citation_f1,
    citation_precision,
    citation_recall,
    cited_chunk_ratio,
    resolve_claim_passage_ids,
    supporting_passage_ids,
)
from app.services.conversation_types import (
    ConversationRequest,
    ConversationState,
    build_initial_state,
    utc_now_iso,
)
from app.services.retrieval_trace import (
    STAGE_BASE,
    STAGE_FINAL_CONTEXT,
    STAGE_MERGED,
    STAGE_PASS_ONE,
    STAGE_PASS_TWO,
    RetrievalTrace,
)
from app.services.metrics_facts import (
    MetricsFactStore,
    build_turn_fact,
    confidence_level,
    create_metrics_fact_store,
)
from shared.metrics import METRICS


# The nodes that consume the selected context. They are the last point at
# which `retrieved_chunks` can still change: evaluation, revision, output
# guardrails and persistence all read the selection without rewriting it.
GENERATION_NODES = frozenset({"generate_answer", "generate_draft_answer"})


class GuardrailBlockedError(Exception):
    """A deliberate safety decision, not a graph execution failure."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(f"{stage} guardrail blocked the request")

try:  # pragma: no cover
    from langgraph.graph import END, StateGraph

    _HAS_LANGGRAPH = True
except ImportError:  # pragma: no cover
    END = "__end__"
    StateGraph = None
    _HAS_LANGGRAPH = False


class ConversationGraphRunner:
    """Orchestrates regular and extended chat flows using LangGraph when available."""

    def __init__(
        self,
        config: RAGConfig,
        backend_client: ConversationBackendClient,
        store: BaseConversationStore,
        tracer: ConversationTracer,
        logger: Any,
        metrics_facts: Optional[MetricsFactStore] = None,
    ):
        self.config = config
        self.backend_client = backend_client
        self.store = store
        self.tracer = tracer
        self.logger = logger
        self.metrics_facts = metrics_facts or create_metrics_fact_store(config)
        self._secret_key_pattern = re.compile(r"(secret|token|password|auth|credential|bootstrap|mongodb)", re.IGNORECASE)
        self._secret_string_patterns = [
            re.compile(r"mongodb:\/\/[^\s]+", re.IGNORECASE),
            re.compile(r"\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
            re.compile(r":\/\/[^\/\s:@]+:[^@\s]+@", re.IGNORECASE),
        ]

    def _public_review(self, review: Dict[str, Any]) -> Dict[str, Any]:
        """Return the frontend-safe review subset.

        This method is the admin/user boundary for judge output. The
        hallucination verdict and the unsupported-claim count are exposed to
        everyone: they are summary judgements about the answer the user just
        received, and hiding them would leave a reader unable to tell a
        confident answer from an unsupported one.

        The ``claims`` array is deliberately **not** exposed. Claim text is
        the judge quoting the answer back alongside the passages that support
        it, which can echo retrieved document content into a channel that has
        no document-level authorization. It stays in the internal review,
        which only the metrics and debug paths read.
        """
        if not review:
            return {}
        return {
            "review_id": review.get("review_id"),
            "verdict": review.get("verdict"),
            "groundedness_score": review.get("groundedness_score"),
            "completeness_score": review.get("completeness_score"),
            "safety_score": review.get("safety_score"),
            "issues": review.get("issues", []),
            "hallucination_verdict": review.get("hallucination_verdict"),
            "unsupported_claim_count": review.get("unsupported_claim_count"),
            "revision_applied": bool(review.get("revision_applied", False)),
            "model_name": review.get("model_name"),
            "created_at": review.get("created_at"),
        }

    async def run(
        self,
        request: ConversationRequest,
        emitter: BaseConversationEmitter,
        resume: bool = False,
        record_metrics: bool = True,
        retrieval_trace: Optional[RetrievalTrace] = None,
    ) -> Dict[str, Any]:
        """Run the conversation graph and return a normalized result.

        Args:
            request: The normalized conversation request.
            emitter: Where progress events are published.
            resume: Whether to continue from the latest checkpoint.
            record_metrics: Whether this turn contributes to Prometheus and
                to `metrics_turn_facts`. The eval harness passes False: its
                turns are synthetic, and letting a few hundred of them into
                the fact collection would move the tenant quality averages an
                eval run exists to measure.
            retrieval_trace: A collector for this turn's candidate lineage,
                or None. Passed only by the eval harness: a user's turn does
                no trace work and its result carries no trace field, which is
                what keeps the normal response payload unchanged.
        """
        runtime = {
            "request": request,
            "emitter": emitter,
            "current_node": "graph_start",
            "retrieval_trace": retrieval_trace,
            # Bounded per-call LLM evidence for this turn, in call order. No
            # prompt, output or context text ever enters it.
            "llm_actions": [],
        }
        state = build_initial_state(request)
        checkpoint = None
        if resume:
            checkpoint = self.store.get_latest_checkpoint(request.conversation_id, request.request_id)
            if checkpoint and checkpoint.get("state"):
                state = checkpoint["state"]
            if checkpoint and checkpoint.get("graph_run_id"):
                request.graph_run_id = checkpoint["graph_run_id"]
            if (
                checkpoint
                and checkpoint.get("owner_id")
                and (request.owner_id == request.conversation_id or not request.owner_id)
            ):
                request.owner_id = checkpoint["owner_id"]
            if (
                checkpoint
                and checkpoint.get("owner_type")
                and request.owner_type in {None, "conversation"}
            ):
                request.owner_type = checkpoint["owner_type"]
        if checkpoint is None:
            self.backend_client.publish_turn_started(request)

        metadata = {
            "service": "rag",
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "mode": request.mode,
            "trace_id": request.trace_id,
            "request_id": request.request_id,
            "correlation_id": request.correlation_id,
            "graph_run_id": request.graph_run_id,
            "chunk_count": len(state["retrieved_chunks"]),
            "model_name": request.model or "default",
        }

        t0 = time.monotonic()
        try:
            with self.tracer.run("rag_conversation_graph", metadata) as trace_metadata:
                if checkpoint and checkpoint.get("stage"):
                    final_state = await self._resume_from_checkpoint(state, runtime, checkpoint["stage"])
                elif _HAS_LANGGRAPH:
                    graph = self._build_graph(runtime)
                    final_state = await graph.ainvoke(state)
                else:
                    final_state = await self._run_fallback_graph(state, runtime)
                trace_metadata["chunk_count"] = len(final_state.get("retrieved_chunks", []))
            # The context generation actually ran on. Normally already
            # committed at the generation boundary; committed here only for a
            # run whose remaining nodes never reached generation (a resume
            # past it, or a flow that produced no answer).
            self._commit_final_context(runtime, final_state)
            final_chunks = runtime["final_context"]
            result = self._build_result(final_state, sources=final_chunks)
            result["llm_actions"] = self._llm_actions(runtime)
            if record_metrics:
                self._record_turn_metrics(
                    request, result, runtime, emitter, time.monotonic() - t0
                )
            return result
        except GuardrailBlockedError as exc:
            self.logger.info(
                "conversation guardrail blocked",
                data={
                    "outcome": "guardrail_blocked",
                    "guardrail_stage": exc.stage,
                    "conversation_id": request.conversation_id,
                    "turn_id": request.turn_id,
                    "request_id": request.request_id,
                },
            )
            self._save_checkpoint(
                request, state, runtime.get("current_node", "unknown"), "guardrail_blocked",
                "guardrail_blocked", {"outcome": "guardrail_blocked", "guardrail_stage": exc.stage},
            )
            result = {
                "answer": "", "sources": [], "review": {}, "citation_metrics": {},
                "outcome": "guardrail_blocked", "guardrail_stage": exc.stage,
                "llm_actions": self._llm_actions(runtime),
            }
            if record_metrics:
                self._record_turn_metrics(request, result, runtime, emitter, time.monotonic() - t0)
            return result
        except Exception as exc:
            failed_node = runtime.get("current_node", "unknown")
            # A downstream LLM reply that failed still reported what the
            # provider did before this service rejected it. Losing that with
            # the exception is what made an output-ceiling truncation
            # indistinguishable from a malformed normal completion.
            if isinstance(exc, DownstreamRPCError):
                self._record_llm_failure_evidence(runtime, exc)
            self.logger.exception(
                "conversation graph execution failed",
                error=str(exc),
                data={
                    "failed_node": failed_node,
                    "conversation_id": request.conversation_id,
                    "turn_id": request.turn_id,
                    "request_id": request.request_id,
                },
            )
            self._save_checkpoint(request, state, failed_node, "error", "error", {"error": str(exc)})
            if not emitter.terminal_sent:
                await emitter.emit(
                    "error",
                    {
                        "code": "graph_execution_error",
                        "failed_node": failed_node,
                        "retryable": True,
                        "message": str(exc),
                    },
                )
            # A failure after the context was chosen does not unmake the
            # retrieval that succeeded: the last authoritative context is
            # returned with the failure, from graph state rather than from
            # any reconstruction. Before that point there is nothing to
            # report, and an empty list there means "unknown", not "none".
            known_context = runtime.get("final_context")
            result = {
                "answer": "",
                "sources": list(known_context) if known_context is not None else [],
                "review": {},
                "citation_metrics": {},
                # Explicit, so no reader can default this result to success.
                "outcome": "failed",
                "error": str(exc),
                "error_class": type(exc).__name__,
                "failed_node": failed_node,
                "llm_actions": self._llm_actions(runtime),
            }
            if record_metrics:
                # The turn fact describes a turn that finished. Keeping the
                # known context on the failure result is for the caller and
                # the eval trace; letting it into the live retrieval averages
                # would move dashboards that have only ever counted completed
                # turns.
                self._record_turn_metrics(
                    request,
                    {**result, "sources": []},
                    runtime,
                    emitter,
                    time.monotonic() - t0,
                    error=exc,
                )
            return result

    def _record_turn_metrics(
        self,
        request: ConversationRequest,
        result: Dict[str, Any],
        runtime: Dict[str, Any],
        emitter: BaseConversationEmitter,
        elapsed: float,
        error: Optional[Exception] = None,
    ) -> None:
        """Record the Prometheus series and the Mongo fact for one finished turn.

        Logs and swallows every failure: a metrics write must never fail a
        user's turn.
        """
        try:
            status = "error" if error is not None else "success"
            # Error latency is recorded too, otherwise slow failures are invisible.
            METRICS.rag_query_duration.labels(
                service="rag",
                answer_mode=request.mode,
            ).observe(elapsed)
            METRICS.rag_queries_total.labels(
                service="rag",
                answer_mode=request.mode,
                status=status,
            ).inc()

            review = result.get("review") or {}
            sources = result.get("sources") or []
            if error is None:
                METRICS.rag_sources_per_query.labels(service="rag").observe(len(sources))
                scores = [
                    float(chunk["score"])
                    for chunk in sources
                    if isinstance(chunk, dict) and chunk.get("score") is not None
                ]
                if scores:
                    # Top chunk only. One observation per chunk would inflate the
                    # sample count and make the histogram mean meaningless.
                    METRICS.rag_retrieval_score.labels(service="rag").observe(max(scores))
                level = confidence_level(review.get("groundedness_score"))
                if level is not None:
                    METRICS.rag_confidence_level.labels(service="rag", level=level).inc()

                # Nothing is observed for an unmeasured value. A skipped
                # observation is correct; a 0.0 would be a lie about an answer
                # nobody measured.
                citation_metrics = result.get("citation_metrics") or {}
                verdict = review.get("hallucination_verdict")
                if verdict is not None:
                    METRICS.rag_hallucination_total.labels(
                        service="rag", verdict=verdict
                    ).inc()
                precision = citation_metrics.get("citation_precision")
                if precision is not None:
                    METRICS.rag_citation_precision.labels(service="rag").observe(precision)
                recall = citation_metrics.get("citation_recall")
                if recall is not None:
                    METRICS.rag_citation_recall.labels(service="rag").observe(recall)

            self.metrics_facts.save_fact(
                build_turn_fact(
                    request,
                    result,
                    {
                        "latency_ms": round(elapsed * 1000, 2),
                        "ttft_ms": (
                            round(emitter.ttft_seconds * 1000, 2)
                            if emitter.ttft_seconds is not None
                            else None
                        ),
                        "stage_ms": runtime.get("stage_ms", {}),
                        "reranker_changed_top1": runtime.get("reranker_changed_top1"),
                        "guardrail_blocked": runtime.get("guardrail_blocked"),
                        "model": runtime.get("model"),
                        "usage": runtime.get("usage"),
                        "error_class": type(error).__name__ if error is not None else None,
                    },
                )
            )
        except Exception as metrics_error:
            self.logger.exception(
                "turn metrics recording failed",
                error=str(metrics_error),
                data={
                    "conversation_id": request.conversation_id,
                    "turn_id": request.turn_id,
                },
            )

    def _build_graph(self, runtime: Dict[str, Any]):
        workflow = StateGraph(ConversationState)
        for name, func in self._node_map().items():
            workflow.add_node(name, self._wrap_node(name, func, runtime))

        workflow.set_entry_point("input_guardrails")
        workflow.add_edge("input_guardrails", "load_short_term_context")
        workflow.add_conditional_edges(
            "load_short_term_context",
            self._select_mode,
            {"regular": "load_memory_light", "extended": "load_memory_deep"},
        )
        workflow.add_edge("load_memory_light", "retrieve_chunks_once")
        workflow.add_edge("retrieve_chunks_once", "generate_answer")
        workflow.add_edge("generate_answer", "evaluate_answer_light")
        workflow.add_edge("evaluate_answer_light", "output_guardrails")
        workflow.add_edge("load_memory_deep", "rewrite_or_decompose_query")
        workflow.add_edge("rewrite_or_decompose_query", "retrieve_pass_one")
        workflow.add_edge("retrieve_pass_one", "rerank_and_merge")
        workflow.add_edge("rerank_and_merge", "retrieve_pass_two_if_needed")
        workflow.add_edge("retrieve_pass_two_if_needed", "generate_draft_answer")
        workflow.add_edge("generate_draft_answer", "evaluate_answer_deep")
        workflow.add_edge("evaluate_answer_deep", "revise_once_if_needed")
        workflow.add_edge("revise_once_if_needed", "output_guardrails")
        workflow.add_edge("output_guardrails", "persist_turn")
        workflow.add_edge("persist_turn", "stream_done")
        workflow.add_edge("stream_done", END)
        return workflow.compile()

    async def _run_fallback_graph(self, state: ConversationState, runtime: Dict[str, Any]) -> ConversationState:
        state = await self._wrap_node("input_guardrails", self._input_guardrails, runtime)(state)
        state = await self._wrap_node("load_short_term_context", self._load_short_term_context, runtime)(state)
        if self._select_mode(state) == "regular":
            names = [
                "load_memory_light",
                "retrieve_chunks_once",
                "generate_answer",
                "evaluate_answer_light",
            ]
        else:
            names = [
                "load_memory_deep",
                "rewrite_or_decompose_query",
                "retrieve_pass_one",
                "rerank_and_merge",
                "retrieve_pass_two_if_needed",
                "generate_draft_answer",
                "evaluate_answer_deep",
                "revise_once_if_needed",
            ]
        mapping = self._node_map()
        for name in names:
            state = await self._wrap_node(name, mapping[name], runtime)(state)
        state = await self._wrap_node("output_guardrails", self._output_guardrails, runtime)(state)
        state = await self._wrap_node("persist_turn", self._persist_turn, runtime)(state)
        state = await self._wrap_node("stream_done", self._stream_done, runtime)(state)
        return state

    async def _resume_from_checkpoint(
        self,
        state: ConversationState,
        runtime: Dict[str, Any],
        stage: str,
    ) -> ConversationState:
        """Resume from the closest configured checkpoint stage."""
        regular_remaining = {
            "graph_start": [
                "input_guardrails",
                "load_short_term_context",
                "load_memory_light",
                "retrieve_chunks_once",
                "generate_answer",
                "evaluate_answer_light",
                "output_guardrails",
                "persist_turn",
                "stream_done",
            ],
            "after_context_load": [
                "load_memory_light",
                "retrieve_chunks_once",
                "generate_answer",
                "evaluate_answer_light",
                "output_guardrails",
                "persist_turn",
                "stream_done",
            ],
            "after_retrieval": [
                "generate_answer",
                "evaluate_answer_light",
                "output_guardrails",
                "persist_turn",
                "stream_done",
            ],
            "after_generation": [
                "evaluate_answer_light",
                "output_guardrails",
                "persist_turn",
                "stream_done",
            ],
            "after_evaluation": [
                "output_guardrails",
                "persist_turn",
                "stream_done",
            ],
            "after_persistence": ["stream_done"],
        }
        extended_remaining = {
            "graph_start": [
                "input_guardrails",
                "load_short_term_context",
                "load_memory_deep",
                "rewrite_or_decompose_query",
                "retrieve_pass_one",
                "rerank_and_merge",
                "retrieve_pass_two_if_needed",
                "generate_draft_answer",
                "evaluate_answer_deep",
                "revise_once_if_needed",
                "output_guardrails",
                "persist_turn",
                "stream_done",
            ],
            "after_context_load": [
                "load_memory_deep",
                "rewrite_or_decompose_query",
                "retrieve_pass_one",
                "rerank_and_merge",
                "retrieve_pass_two_if_needed",
                "generate_draft_answer",
                "evaluate_answer_deep",
                "revise_once_if_needed",
                "output_guardrails",
                "persist_turn",
                "stream_done",
            ],
            "after_retrieval": [
                "generate_draft_answer",
                "evaluate_answer_deep",
                "revise_once_if_needed",
                "output_guardrails",
                "persist_turn",
                "stream_done",
            ],
            "after_generation": [
                "evaluate_answer_deep",
                "revise_once_if_needed",
                "output_guardrails",
                "persist_turn",
                "stream_done",
            ],
            "after_evaluation": [
                "revise_once_if_needed",
                "output_guardrails",
                "persist_turn",
                "stream_done",
            ],
            "after_persistence": ["stream_done"],
        }
        mapping = self._node_map()
        remaining = (regular_remaining if self._select_mode(state) == "regular" else extended_remaining).get(stage)
        if not remaining:
            return await self._run_fallback_graph(state, runtime)
        for name in remaining:
            state = await self._wrap_node(name, mapping[name], runtime)(state)
        return state

    def _node_map(self) -> Dict[str, Any]:
        return {
            "input_guardrails": self._input_guardrails,
            "load_short_term_context": self._load_short_term_context,
            "load_memory_light": self._load_memory_light,
            "retrieve_chunks_once": self._retrieve_chunks_once,
            "generate_answer": self._generate_answer,
            "evaluate_answer_light": self._evaluate_answer_light,
            "load_memory_deep": self._load_memory_deep,
            "rewrite_or_decompose_query": self._rewrite_or_decompose_query,
            "retrieve_pass_one": self._retrieve_pass_one,
            "rerank_and_merge": self._rerank_and_merge,
            "retrieve_pass_two_if_needed": self._retrieve_pass_two_if_needed,
            "generate_draft_answer": self._generate_draft_answer,
            "evaluate_answer_deep": self._evaluate_answer_deep,
            "revise_once_if_needed": self._revise_once_if_needed,
            "output_guardrails": self._output_guardrails,
            "persist_turn": self._persist_turn,
            "stream_done": self._stream_done,
        }

    def _wrap_node(self, name: str, func, runtime: Dict[str, Any]):
        async def node(state: ConversationState) -> ConversationState:
            runtime["current_node"] = name
            if name in GENERATION_NODES:
                # Before the node runs: the context entering generation is
                # the context generation uses, and it must survive the node
                # failing.
                self._commit_final_context(runtime, state)
            emitter: BaseConversationEmitter = runtime["emitter"]
            request: ConversationRequest = runtime["request"]
            started = time.monotonic()
            span_name = {
                "load_memory_light": "load_memory",
                "load_memory_deep": "load_memory",
                "retrieve_chunks_once": "retrieve_chunks",
                "retrieve_pass_one": "retrieve_chunks",
                "retrieve_pass_two_if_needed": "retrieve_chunks",
                "rerank_and_merge": "rerank",
                "generate_draft_answer": "generate_answer",
                "evaluate_answer_light": "evaluate_answer",
                "evaluate_answer_deep": "evaluate_answer",
                "revise_once_if_needed": "revise_if_needed",
            }.get(name, name)
            await emitter.emit("status", {"node": name, "phase": "started", "message": f"{name} started", "mode": request.mode})
            with self.tracer.span(
                span_name,
                {
                    "conversation_id": request.conversation_id,
                    "turn_id": request.turn_id,
                    "request_id": request.request_id,
                    "trace_id": request.trace_id,
                    "correlation_id": request.correlation_id,
                    "graph_run_id": request.graph_run_id,
                    "mode": request.mode,
                },
            ):
                update = await func(copy.deepcopy(state), runtime)
            meta = update.pop("_meta", {})
            phase = meta.get("phase", "completed")
            trace_payload = {
                "node": name,
                "event": phase,
                "decision": meta.get("decision", phase),
                "counters": meta.get("counters", {}),
                "latency": round((time.monotonic() - started) * 1000, 2),
            }
            METRICS.rag_stage_duration.labels(service="rag", stage=span_name).observe(
                time.monotonic() - started
            )
            # Carried on `runtime` (one dict per turn) for the turn fact. Retrieval
            # runs more than once per extended turn, so stages accumulate.
            stage_ms = runtime.setdefault("stage_ms", {})
            stage_ms[span_name] = stage_ms.get(span_name, 0.0) + trace_payload["latency"]
            if meta.get("debug_excerpt"):
                trace_payload["debug_excerpt"] = self._truncate(meta["debug_excerpt"])
            trace_events = list(update.get("trace_events", state.get("trace_events", [])))
            trace_events.append(trace_payload)
            update["trace_events"] = trace_events
            next_state = copy.deepcopy(state)
            next_state.update(update)
            if name == "stream_done" and emitter.terminal_sent:
                return next_state
            await emitter.emit(
                "status",
                {
                    "node": name,
                    "phase": phase,
                    "message": meta.get("message", f"{name} {phase}"),
                    "progress": meta.get("progress"),
                    "mode": request.mode,
                },
            )
            await emitter.emit("trace", trace_payload)
            return next_state

        return node

    def _select_mode(self, state: ConversationState) -> str:
        return state.get("mode", "regular")

    def _truncate(self, value: Any) -> Any:
        safe = self._sanitize_debug_value(make_json_safe(value))
        if isinstance(safe, str):
            return safe[: self.config.debug_payload_max_chars]
        if isinstance(safe, list):
            return safe[: self.config.debug_payload_max_items]
        if isinstance(safe, dict):
            trimmed: Dict[str, Any] = {}
            for index, (key, item) in enumerate(safe.items()):
                if index >= self.config.debug_payload_max_items:
                    break
                trimmed[key] = self._truncate(item)
            return trimmed
        return safe

    def _sanitize_debug_value(self, value: Any) -> Any:
        """Redact obvious secrets from debug-visible payloads."""
        if isinstance(value, dict):
            sanitized: Dict[str, Any] = {}
            for key, item in value.items():
                if self._secret_key_pattern.search(str(key)):
                    sanitized[str(key)] = "[redacted]"
                else:
                    sanitized[str(key)] = self._sanitize_debug_value(item)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize_debug_value(item) for item in value]
        if isinstance(value, str):
            sanitized = value
            for pattern in self._secret_string_patterns:
                sanitized = pattern.sub("[redacted]", sanitized)
            return sanitized
        return value

    def _append_debug(self, state: ConversationState, **payloads: Any) -> Dict[str, Any]:
        if not self.config.allow_debug_payloads:
            return {}
        debug_payloads = dict(state.get("debug_payloads", {}))
        for key, value in payloads.items():
            debug_payloads[key] = self._truncate(value)
        return debug_payloads

    def _structured_output_debug_payloads(self, response: Dict[str, Any], prefix: str) -> Dict[str, Any]:
        metadata = response.get("_structured_output_debug")
        if not isinstance(metadata, dict):
            return {}
        return {
            f"{prefix}_structured_output_candidates": metadata.get("candidates", []),
            f"{prefix}_structured_output_selected_index": metadata.get("selected_payload_index"),
            f"{prefix}_structured_output_selection_policy": metadata.get("selection_policy"),
            f"{prefix}_structured_output_extraction_mode": metadata.get("extraction_mode"),
            f"{prefix}_raw_output": response.get("raw_output"),
        }

    def _trace_stage(
        self,
        runtime: Dict[str, Any],
        stage: str,
        chunks: List[Dict[str, Any]],
        *,
        query: Optional[str] = None,
        query_source: Optional[str] = None,
        returned_count: Optional[int] = None,
    ) -> None:
        """Report one retrieval step to this turn's collector, if it has one.

        A no-op on a user's turn: the eval harness is the only caller that
        supplies a collector, so nothing here costs a normal turn anything.
        """
        trace: Optional[RetrievalTrace] = runtime.get("retrieval_trace")
        if trace is None:
            return
        trace.record_stage(
            stage,
            chunks,
            query=query,
            query_source=query_source,
            returned_count=returned_count,
        )

    def _commit_final_context(
        self,
        runtime: Dict[str, Any],
        state: ConversationState,
    ) -> None:
        """Freeze the context the answer will be generated from.

        Called at the boundary into generation, which is the last node that
        can still change ``retrieved_chunks``: everything after it reads the
        selection without rewriting it. Recording the terminal context only
        after the whole graph returned meant that a failure in generation,
        the judge, an output guardrail or persistence erased retrieval
        evidence that was already known — and an eval row with no final
        context then read as a retrieval miss rather than as the downstream
        failure it was.

        Committed once. The first commit wins, so a later re-entry into
        generation (a revision pass) cannot write a second, contradicting
        terminal stage.
        """
        if runtime.get("final_context") is not None:
            return
        chunks = list(state.get("retrieved_chunks", []) or [])
        runtime["final_context"] = chunks
        self._trace_stage(runtime, STAGE_FINAL_CONTEXT, chunks)

    def _trace_decision(
        self,
        runtime: Dict[str, Any],
        stage: str,
        decision: str,
        *,
        reason: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Report one pipeline branch to this turn's collector, if it has one."""
        trace: Optional[RetrievalTrace] = runtime.get("retrieval_trace")
        if trace is None:
            return
        trace.record_decision(stage, decision, reason=reason, detail=detail)

    def _normalize_chunks(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        chunks = payload.get("chunks") or payload.get("results") or []
        normalized = []
        for item in chunks:
            # Qdrant returns fields nested under "payload"; support both flat and nested shapes
            qdrant_payload = item.get("payload", {}) or {}
            metadata = item.get("metadata", {}) or qdrant_payload.get("metadata", {}) or {}
            text = (
                item.get("text")
                or item.get("chunk")
                or item.get("content")
                or qdrant_payload.get("text")
                or metadata.get("text", "")
            )
            if not text:
                continue
            review_status = item.get("review_status") or qdrant_payload.get("review_status") or metadata.get("review_status") or "clean"
            retrieval_allowed = bool(item.get("retrieval_allowed", qdrant_payload.get("retrieval_allowed", metadata.get("retrieval_allowed", True))))
            # Counted where the policy decision is made, so the filtered rate's
            # denominator matches its numerator. Chunks dropped just above for
            # empty text never reach here: that is a data-quality drop, not a
            # policy one, and folding it in would dilute the rate.
            METRICS.rag_chunks_considered_total.labels(service="rag").inc()
            if not retrieval_allowed:
                METRICS.rag_chunks_filtered_total.labels(
                    service="rag", reason="retrieval_not_allowed"
                ).inc()
                continue
            if review_status == "removed":
                METRICS.rag_chunks_filtered_total.labels(
                    service="rag", reason="review_removed"
                ).inc()
                continue
            chunk_index = item.get("chunk_index") or qdrant_payload.get("chunk_index") or metadata.get("chunk_index") or len(normalized)
            chunk_version = item.get("chunk_version") or qdrant_payload.get("chunk_version") or metadata.get("chunk_version") or 1
            source_name = (
                item.get("source_name")
                or item.get("source")
                or qdrant_payload.get("source_name")
                or metadata.get("filename")
                or metadata.get("source_name")
                or ""
            )
            document_id = (
                item.get("document_id")
                or item.get("file_id")
                or qdrant_payload.get("document_id")
                or qdrant_payload.get("file_id")
                or metadata.get("document_id")
                or metadata.get("file_id")
                or source_name
                or item.get("chunk_id")
                or qdrant_payload.get("chunk_id")
                or item.get("id")
                or f"document-{chunk_index}"
            )
            file_id = item.get("file_id") or qdrant_payload.get("file_id") or metadata.get("file_id") or document_id
            normalized.append(
                {
                    "file_id": file_id,
                    "document_id": document_id,
                    "chunk_id": (
                        item.get("chunk_id")
                        or qdrant_payload.get("chunk_id")
                        or item.get("id")
                        or f"{document_id or 'document'}__v{chunk_version}__c{chunk_index}"
                    ),
                    "chunk_index": chunk_index,
                    "chunk_version": chunk_version,
                    "text": text,
                    "text_preview": (item.get("text_preview") or qdrant_payload.get("text_preview") or text[:240]),
                    "source_name": source_name,
                    "page": item.get("page") or qdrant_payload.get("page") or metadata.get("page"),
                    "section": item.get("section") or qdrant_payload.get("section") or metadata.get("section"),
                    "retrieval_allowed": retrieval_allowed,
                    "review_status": review_status,
                    "issue_flags": self._truncate(item.get("issue_flags") or qdrant_payload.get("issue_flags") or metadata.get("issue_flags") or []),
                    "created_at": item.get("created_at") or qdrant_payload.get("created_at") or metadata.get("created_at") or utc_now_iso(),
                    "score": item.get("score", item.get("similarity", 0.0)),
                    "source": source_name,
                    "metadata": self._truncate(metadata),
                }
            )
        return normalized

    def _build_prompt(
        self,
        state: ConversationState,
        request: ConversationRequest,
        mode: str,
        review_issues: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        passages = self._prompt_passages(state)
        retrieved_context = [passage["text"] for passage in passages]
        memory_context = "\n".join(str(item.get("content", "")) for item in state.get("memory_hits", []))
        parts = [f"Mode: {mode}", f"Conversation summary:\n{state.get('short_term_summary', '')}"]
        if state.get("recent_messages"):
            history_lines = []
            for msg in state["recent_messages"]:
                role = "User" if msg.get("role") == "user" else "Assistant"
                history_lines.append(f"{role}: {msg.get('content', '')}")
            parts.append("Recent messages:\n" + "\n".join(history_lines))
        if memory_context:
            parts.append(f"Relevant memory:\n{memory_context}")
        if state.get("retrieval_plan"):
            parts.append(f"Retrieval plan:\n{state['retrieval_plan']}")
        if retrieved_context:
            parts.append(f"Retrieved context:\n{retrieved_context}")
        if review_issues:
            parts.append(f"Fix these issues:\n{review_issues}")
        parts.append(
            "Answer grounded in the retrieved context when relevant. Be helpful, clear, and explicit about uncertainty. "
            "Return the answer only."
        )
        return {
            "instructions": "\n\n".join(parts),
            # Passages, not bare strings: llm_agent numbers them [1], [2], ...
            # and resolves the answer's citation markers back through this
            # same order to `source_id`.
            "retrieved_context": passages,
            "recent_messages": state.get("recent_messages", []),
            "revision_attempted": bool(review_issues),
        }

    def _prompt_passages(self, state: ConversationState) -> List[Dict[str, Any]]:
        """Return the citable passages for this turn, in citation order.

        Generation and evaluation are given the *same* list. If the judge saw
        a different set, or the same set in a different order, its passage
        numbers and the answer's citation markers would name different chunks
        and every citation metric computed from them would be noise.
        """
        return chunk_passages(
            state.get("retrieved_chunks", [])[: self.config.top_k_documents]
        )

    def _build_review(
        self,
        payload: Dict[str, Any],
        request: ConversationRequest,
        passages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Normalize a judge reply into the internal review record.

        Claim-level fields are carried through here and kept internal; see
        `_public_review` for what leaves the service. The judge answers in
        passage numbers, so its references are translated into chunk ids
        against `passages` — the same list the answer's citations resolve
        against — before anything compares the two.
        """
        claims = resolve_claim_passage_ids(
            payload.get("claims") or [],
            [passage["source_id"] for passage in (passages or [])],
        )
        unsupported = payload.get("unsupported_claim_count")
        return {
            "review_id": payload.get("review_id") or str(uuid4()),
            "verdict": payload.get("verdict", "pass"),
            "groundedness_score": float(payload.get("groundedness_score") or 0.0),
            "completeness_score": float(payload.get("completeness_score") or 0.0),
            "safety_score": float(payload.get("safety_score") or 0.0),
            "issues": payload.get("issues", []),
            "claims": claims,
            "unsupported_claim_count": (
                sum(1 for claim in claims if not claim.get("supported"))
                if claims
                else (int(unsupported) if unsupported is not None else None)
            ),
            "hallucination_verdict": payload.get("hallucination_verdict"),
            "revision_applied": bool(payload.get("revision_applied", False)),
            "model_name": payload.get("model_name") or request.model or "default",
            "created_at": payload.get("created_at") or utc_now_iso(),
            "should_revise": bool(payload.get("should_revise", False)),
        }

    def _summarize_turn(self, state: ConversationState) -> str:
        existing = state.get("short_term_summary", "").strip()
        snippet = f"User: {state.get('user_message', '')} Assistant: {state.get('draft_answer', {}).get('text', '')}"
        return f"{existing} {snippet}".strip()[: self.config.debug_payload_max_chars]

    def _save_checkpoint(
        self,
        request: ConversationRequest,
        state: ConversationState,
        node: str,
        stage: str,
        status: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "request_id": request.request_id,
            "trace_id": request.trace_id,
            "graph_run_id": request.graph_run_id,
            "correlation_id": request.correlation_id,
            "owner_id": request.owner_id,
            "owner_type": request.owner_type,
            "node": node,
            "stage": stage,
            "status": status,
            "state": make_json_safe(state),
            "created_at": utc_now_iso(),
        }
        if extra:
            payload.update(make_json_safe(extra))
        self.store.save_checkpoint(payload)

    @staticmethod
    def _record_llm_evidence(runtime: Dict[str, Any], response: Any) -> None:
        """Keep one typed LLM call's bounded evidence on this turn.

        Recorded for successful calls too: proving that a failing evaluator
        stopped at its output ceiling needs the distribution of the calls that
        did not fail as its comparison.
        """
        evidence = (
            response.get(LLM_EVIDENCE_KEY) if isinstance(response, dict) else None
        )
        if isinstance(evidence, dict):
            runtime.setdefault("llm_actions", []).append(dict(evidence))

    @staticmethod
    def _record_llm_failure_evidence(runtime: Dict[str, Any], exc: BaseException) -> None:
        """Keep the evidence a failed downstream LLM reply already carried."""
        evidence = getattr(exc, "evidence", None)
        if isinstance(evidence, dict):
            runtime.setdefault("llm_actions", []).append(dict(evidence))

    @staticmethod
    def _llm_actions(runtime: Dict[str, Any]) -> List[Dict[str, Any]]:
        actions = runtime.get("llm_actions")
        return list(actions) if isinstance(actions, list) else []

    def _build_result(
        self,
        state: ConversationState,
        *,
        sources: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        final_sources = (
            state.get("retrieved_chunks", []) if sources is None else sources
        )
        return {
            "answer": state.get("draft_answer", {}).get("text", ""),
            "sources": final_sources,
            "citations": state.get("draft_answer", {}).get("citations"),
            "review": self._public_review(state.get("answer_review", {})),
            # Numbers only, derived from the internal review. The claim text
            # they were computed from does not travel with them.
            "citation_metrics": self._citation_metrics(state),
            "trace_events": state.get("trace_events", []),
            "debug_payloads": state.get("debug_payloads", {}),
            "outcome": state.get("outcome", "success"),
            "guardrail_stage": state.get("guardrail_stage"),
        }

    def _citation_metrics(self, state: ConversationState) -> Dict[str, Any]:
        """Compute this turn's citation figures from the answer and the judge.

        Every value is None when the corresponding measurement did not
        happen: citations off or absent, judge unavailable, nothing
        retrieved. A turn that was not measured must contribute nothing to an
        average rather than a zero.
        """
        draft = state.get("draft_answer", {}) or {}
        review = state.get("answer_review", {}) or {}
        citations = draft.get("citations")
        if citations is None:
            return {
                "citation_count": None,
                "cited_chunk_ratio": None,
                "citation_precision": None,
                "citation_recall": None,
                "citation_f1": None,
            }

        cited_ids = [
            str(citation.get("source_id"))
            for citation in citations
            if isinstance(citation, dict) and citation.get("source_id")
        ]
        claims = review.get("claims") or []
        # No claims means the judge did not run or returned nothing usable:
        # precision has no support set to check against, so it is unmeasured
        # rather than zero.
        precision = (
            citation_precision(cited_ids, supporting_passage_ids(claims))
            if claims
            else None
        )
        recall = citation_recall(claims, set(cited_ids)) if claims else None
        return {
            "citation_count": len(citations),
            "cited_chunk_ratio": cited_chunk_ratio(
                cited_ids, len(self._prompt_passages(state))
            ),
            "citation_precision": precision,
            "citation_recall": recall,
            "citation_f1": citation_f1(precision, recall),
        }

    async def _input_guardrails(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        user_message = request.user_message.strip()
        if not user_message:
            raise ValueError("Question is required")
        scan = await self.backend_client.risk_scan(request, user_message, stage="input")
        self._record_llm_evidence(runtime, scan)
        debug_payloads = self._append_debug(state, input_safety_flags=scan)
        if scan.get("blocked"):
            runtime["guardrail_blocked"] = True
            raise GuardrailBlockedError("input")
        snapshot = copy.deepcopy(state)
        snapshot["user_message"] = user_message
        snapshot["debug_payloads"] = debug_payloads
        self._save_checkpoint(request, snapshot, "input_guardrails", "graph_start", "started")
        return {
            "mode": request.mode,
            "user_message": user_message,
            "debug_payloads": debug_payloads,
            "_meta": {"message": "Input validated", "debug_excerpt": scan.get("message") or "input accepted"},
        }

    async def _load_short_term_context(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        context = self.store.load_context(request.conversation_id, self.config.max_recent_messages)
        summary = context.get("summary") or state.get("short_term_summary", "")
        recent_messages = context.get("recent_messages") or state.get("recent_messages", [])
        snapshot = copy.deepcopy(state)
        snapshot["short_term_summary"] = summary
        snapshot["recent_messages"] = recent_messages
        self._save_checkpoint(request, snapshot, "load_short_term_context", "after_context_load", "ok")
        return {
            "short_term_summary": summary,
            "recent_messages": recent_messages,
            "_meta": {
                "message": "Short-term context loaded",
                "counters": {"recent_messages": len(recent_messages)},
                "debug_excerpt": (summary or "")[:120],
            },
        }

    async def _load_memory_light(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        response = await self.backend_client.get_relevant_memories(request, depth="light")
        memories = response.get("memories") or response.get("items") or []
        return {
            "memory_hits": self._truncate(memories[: self.config.max_memory_hits]),
            "_meta": {
                "message": "Light memory loaded",
                "counters": {"memory_hits": len(memories)},
                "debug_excerpt": str(memories[:1])[:120],
            },
        }

    async def _load_memory_deep(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        response = await self.backend_client.get_relevant_memories(request, depth="deep")
        memories = response.get("memories") or response.get("items") or []
        return {
            "memory_hits": self._truncate(memories[: self.config.max_memory_hits]),
            "_meta": {
                "message": "Deep memory loaded",
                "counters": {"memory_hits": len(memories)},
                "debug_excerpt": str(memories[:1])[:120],
            },
        }

    async def _retrieve_chunks_once(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        response = await self.backend_client.search_chunks(request, request.user_message, state.get("retrieval_plan", {}), "regular")
        chunks = self._normalize_chunks(response)
        self._trace_stage(
            runtime,
            STAGE_BASE,
            chunks,
            query=request.user_message,
            query_source="user_message",
            returned_count=len(response.get("chunks") or response.get("results") or []),
        )
        snapshot = copy.deepcopy(state)
        snapshot["retrieved_chunks"] = chunks
        self._save_checkpoint(request, snapshot, "retrieve_chunks_once", "after_retrieval", "ok")
        return {
            "retrieved_chunks": chunks,
            "_meta": {
                "message": "Chunks retrieved",
                "counters": {"chunk_count": len(chunks)},
                "debug_excerpt": (chunks[0]["text"][:120] if chunks else "no chunks"),
            },
        }

    async def _rewrite_or_decompose_query(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        response = await self.backend_client.query_rewrite(
            request,
            {
                "summary": state.get("short_term_summary", ""),
                "recent_messages": state.get("recent_messages", []),
                "memory_hits": state.get("memory_hits", []),
            },
        )
        self._record_llm_evidence(runtime, response)
        plan = {
            "rewritten_query": response.get("rewritten_query") or request.user_message,
            "subqueries": response.get("subqueries") or [],
            "pass_two_hints": response.get("pass_two_hints") or [],
            "decision": response.get("decision", "rewrite"),
        }
        return {
            "retrieval_plan": self._truncate(plan),
            "debug_payloads": self._append_debug(state, rewrite_response=response),
            "_meta": {
                "message": "Query rewrite complete",
                "debug_excerpt": (plan.get("rewritten_query") or request.user_message)[:120],
            },
        }

    async def _retrieve_pass_one(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        plan = state.get("retrieval_plan", {})
        queries = [plan.get("rewritten_query") or request.user_message]
        queries.extend(plan.get("subqueries") or [])
        chunks: List[Dict[str, Any]] = []
        for index, query in enumerate(queries[: self.config.debug_payload_max_items]):
            response = await self.backend_client.search_chunks(request, query, plan, "pass_one")
            normalized = self._normalize_chunks(response)
            self._trace_stage(
                runtime,
                STAGE_PASS_ONE,
                normalized,
                query=query,
                # Which query this was tells a reader whether a miss came
                # from the rewrite or from one decomposed subquery.
                query_source="rewritten_query" if index == 0 else f"subquery_{index}",
                returned_count=len(response.get("chunks") or response.get("results") or []),
            )
            chunks.extend(normalized)
        snapshot = copy.deepcopy(state)
        snapshot["retrieved_chunks"] = chunks
        self._save_checkpoint(request, snapshot, "retrieve_pass_one", "after_retrieval", "ok")
        return {
            "retrieved_chunks": chunks,
            "_meta": {
                "message": "Pass one retrieval complete",
                "counters": {"chunk_count": len(chunks)},
                "debug_excerpt": (chunks[0]["text"][:120] if chunks else "no chunks"),
            },
        }

    async def _rerank_and_merge(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        incoming = state.get("retrieved_chunks", [])
        previous_top = incoming[0].get("chunk_id") if incoming else None
        merged: Dict[str, Dict[str, Any]] = {}
        for chunk in incoming:
            chunk_id = chunk["chunk_id"]
            current = merged.get(chunk_id)
            if current is None or chunk.get("score", 0.0) > current.get("score", 0.0):
                merged[chunk_id] = chunk
        reranked = sorted(merged.values(), key=lambda item: item.get("score", 0.0), reverse=True)
        if previous_top is not None:
            # Only meaningful when something was retrieved; an empty turn has no
            # first-ranked chunk to change.
            changed = reranked[0].get("chunk_id") != previous_top if reranked else False
            runtime["reranker_changed_top1"] = changed
            METRICS.rag_reranker_changed_top1.labels(
                service="rag",
                changed="true" if changed else "false",
            ).inc()
            self._trace_decision(
                runtime,
                STAGE_MERGED,
                "top1_changed" if changed else "top1_unchanged",
                reason="rerank_and_merge",
                detail={"previous_top_chunk_id": previous_top},
            )
        kept = reranked[: self.config.top_k_documents * 2]
        # Recorded after the cap: the merge's own bound is part of why a
        # candidate stopped travelling, and a trace showing the pre-cap list
        # would attribute that loss to the wrong step.
        self._trace_stage(runtime, STAGE_MERGED, kept, returned_count=len(reranked))
        return {
            "retrieved_chunks": kept,
            "_meta": {
                "message": "Chunks reranked and merged",
                "counters": {"chunk_count": len(reranked)},
                "debug_excerpt": f"top_score={reranked[0]['score']:.3f}" if reranked else "no reranked chunks",
            },
        }

    async def _retrieve_pass_two_if_needed(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        chunks = list(state.get("retrieved_chunks", []))
        top_score = chunks[0].get("score", 0.0) if chunks else 0.0
        should_run = (
            len(chunks) < self.config.pass_two_chunk_threshold
            or top_score < self.config.pass_two_score_threshold
            or bool(state.get("retrieval_plan", {}).get("pass_two_hints"))
        )
        if not should_run:
            self._trace_decision(
                runtime,
                STAGE_PASS_TWO,
                "skipped",
                reason="sufficient_pass_one",
                detail={
                    "chunk_count": len(chunks),
                    "top_score": top_score,
                    "chunk_threshold": self.config.pass_two_chunk_threshold,
                    "score_threshold": self.config.pass_two_score_threshold,
                },
            )
            return {
                "_meta": {
                    "phase": "skipped",
                    "decision": "sufficient_pass_one",
                    "message": "Second retrieval skipped",
                    "debug_excerpt": f"top_score={top_score:.3f}",
                }
            }
        alt_query = (
            (state.get("retrieval_plan", {}).get("pass_two_hints") or [None])[0]
            or state.get("retrieval_plan", {}).get("rewritten_query")
            or request.user_message
        )
        self._trace_decision(
            runtime,
            STAGE_PASS_TWO,
            "triggered",
            reason=(
                "pass_two_hint"
                if state.get("retrieval_plan", {}).get("pass_two_hints")
                else "thin_pass_one"
                if len(chunks) < self.config.pass_two_chunk_threshold
                else "low_top_score"
            ),
            detail={
                "chunk_count": len(chunks),
                "top_score": top_score,
                "chunk_threshold": self.config.pass_two_chunk_threshold,
                "score_threshold": self.config.pass_two_score_threshold,
            },
        )
        response = await self.backend_client.search_chunks(request, alt_query, state.get("retrieval_plan", {}), "pass_two")
        second = self._normalize_chunks(response)
        self._trace_stage(
            runtime,
            STAGE_PASS_TWO,
            second,
            query=alt_query,
            query_source=(
                "pass_two_hint"
                if state.get("retrieval_plan", {}).get("pass_two_hints")
                else "rewritten_query"
            ),
            returned_count=len(response.get("chunks") or response.get("results") or []),
        )
        merged = chunks + second
        snapshot = copy.deepcopy(state)
        snapshot["retrieved_chunks"] = merged
        self._save_checkpoint(request, snapshot, "retrieve_pass_two_if_needed", "after_retrieval", "ok")
        return {
            "retrieved_chunks": merged,
            "_meta": {
                "message": "Second retrieval complete",
                "counters": {"chunk_count": len(merged)},
                "debug_excerpt": (merged[0]["text"][:120] if merged else "no chunks"),
            },
        }

    async def _generate_answer(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        return await self._generate_common(
            state,
            runtime,
            source="final",
            mode="regular",
            checkpoint_node="generate_answer",
        )

    async def _generate_draft_answer(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        return await self._generate_common(
            state,
            runtime,
            source="draft",
            mode="extended",
            checkpoint_node="generate_draft_answer",
        )

    async def _generate_common(
        self,
        state: ConversationState,
        runtime: Dict[str, Any],
        source: str,
        mode: str,
        checkpoint_node: str,
        review_issues: Optional[List[str]] = None,
        is_revision: bool = False,
    ) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        emitter: BaseConversationEmitter = runtime["emitter"]
        prompt = self._build_prompt(state, request, mode, review_issues=review_issues)

        async def on_token(text_delta: str, token_index: int) -> None:
            await emitter.emit(
                "token",
                {"text_delta": text_delta, "token_index": token_index, "source": source},
            )

        response = await self.backend_client.generate_answer(
            request,
            prompt=prompt,
            stream_request_id=request.request_id,
            token_callback=on_token,
        )
        self._record_llm_evidence(runtime, response)
        answer_text = response.get("answer", "")
        draft_answer = {
            "text": answer_text,
            # None when citation extraction did not run at all, [] when it ran
            # and the model cited nothing. The two are different facts.
            "citations": response.get("citations"),
            "invalid_citation_count": response.get("invalid_citation_count"),
            "sources": state.get("retrieved_chunks", []),
            "model_name": response.get("model_name") or request.model or "default",
            "created_at": utc_now_iso(),
            "source": source,
            "revision_attempted": bool(is_revision or state.get("draft_answer", {}).get("revision_attempted", False)),
        }
        runtime["model"] = draft_answer["model_name"]
        runtime["usage"] = response.get("usage")
        debug_payloads = self._append_debug(
            state,
            generation_instructions=prompt.get("instructions"),
            generation_context=prompt.get("retrieved_context"),
            raw_output=response.get("raw_output") or answer_text,
            visible_reasoning_summary=response.get("visible_reasoning_summary"),
            raw_prompt=response.get("raw_prompt") or "",
            system_prompt=response.get("system_prompt") or "",
        )
        snapshot = copy.deepcopy(state)
        snapshot["draft_answer"] = draft_answer
        snapshot["debug_payloads"] = debug_payloads
        self._save_checkpoint(request, snapshot, checkpoint_node, "after_generation", "ok")
        return {
            "draft_answer": draft_answer,
            "debug_payloads": debug_payloads,
            "_meta": {
                "message": "Answer generated",
                "counters": {"chunk_count": len(state.get("retrieved_chunks", []))},
                "debug_excerpt": answer_text[:120],
            },
        }

    async def _evaluate_answer_light(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        return await self._evaluate_common(state, runtime, mode="regular")

    async def _evaluate_answer_deep(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        return await self._evaluate_common(state, runtime, mode="extended")

    async def _evaluate_common(self, state: ConversationState, runtime: Dict[str, Any], mode: str) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        emitter: BaseConversationEmitter = runtime["emitter"]
        # The same slice the answer was generated from: citation markers and
        # the judge's passage numbers must index the same list.
        chunks = state.get("retrieved_chunks", [])[: self.config.top_k_documents]
        response = await self.backend_client.evaluate_answer(
            request,
            state.get("draft_answer", {}).get("text", ""),
            chunks,
            mode,
        )
        self._record_llm_evidence(runtime, response)
        review = self._build_review(response, request, self._prompt_passages(state))
        if state.get("draft_answer", {}).get("revision_attempted"):
            review["revision_applied"] = True
        await emitter.emit("answer_review", self._public_review(review))
        debug_payloads = self._append_debug(
            state,
            **self._structured_output_debug_payloads(response, "answer_review"),
        )
        snapshot = copy.deepcopy(state)
        snapshot["answer_review"] = review
        snapshot["debug_payloads"] = debug_payloads
        self._save_checkpoint(request, snapshot, "evaluate_answer", "after_evaluation", "ok")
        return {
            "answer_review": review,
            "debug_payloads": debug_payloads,
            "_meta": {
                "message": "Answer evaluated",
                "counters": {"issues": len(review.get("issues", []))},
                "debug_excerpt": f"verdict={review.get('verdict', 'unknown')}",
            },
        }

    async def _revise_once_if_needed(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        emitter: BaseConversationEmitter = runtime["emitter"]
        review = dict(state.get("answer_review", {}))
        if (
            not review.get("should_revise")
            or review.get("revision_applied")
            or state.get("draft_answer", {}).get("revision_attempted")
        ):
            return {
                "_meta": {
                    "phase": "skipped",
                    "decision": "no_revision_needed",
                    "message": "Revision skipped",
                    "debug_excerpt": f"revision_applied={review.get('revision_applied', False)}",
                }
            }
        updated = await self._generate_common(
            state,
            runtime,
            source="final",
            mode="extended",
            checkpoint_node="revise_once_if_needed",
            review_issues=review.get("issues", []),
            is_revision=True,
        )
        review["revision_applied"] = True
        await emitter.emit("answer_review", self._public_review(review))
        updated["answer_review"] = review
        updated["_meta"] = {"message": "Revision applied", "debug_excerpt": "single revision applied"}
        return updated

    async def _output_guardrails(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        answer_text = state.get("draft_answer", {}).get("text", "")
        response = await self.backend_client.risk_scan(request, answer_text, stage="output")
        self._record_llm_evidence(runtime, response)
        runtime["guardrail_blocked"] = bool(response.get("blocked"))
        draft_answer = dict(state.get("draft_answer", {}))
        if response.get("blocked"):
            self.logger.info(
                "conversation guardrail blocked",
                data={
                    "outcome": "guardrail_blocked",
                    "guardrail_stage": "output",
                    "conversation_id": request.conversation_id,
                    "turn_id": request.turn_id,
                    "request_id": request.request_id,
                },
            )
            draft_answer["text"] = response.get("safe_output") or "I can't help with that request."
        debug_payloads = self._append_debug(
            state,
            output_safety_flags=response,
            **self._structured_output_debug_payloads(response, "output_safety"),
        )
        return {
            "draft_answer": draft_answer,
            "debug_payloads": debug_payloads,
            "outcome": "guardrail_blocked" if response.get("blocked") else "success",
            "guardrail_stage": "output" if response.get("blocked") else None,
            "_meta": {
                "message": "Output guardrails completed",
                "debug_excerpt": response.get("message") or ("blocked" if response.get("blocked") else "clear"),
            },
        }

    async def _persist_turn(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        request: ConversationRequest = runtime["request"]
        review = state.get("answer_review", {})
        summary = self._summarize_turn(state)
        try:
            return await self._do_persist_turn(state, runtime, request, review, summary)
        except Exception as exc:
            self.logger.exception(
                "persist_turn failed — conversation history will NOT be saved",
                error=str(exc),
                data={"conversation_id": request.conversation_id, "turn_id": request.turn_id},
            )
            return {
                "short_term_summary": summary,
                "_meta": {"message": f"Turn persist FAILED: {exc}", "debug_excerpt": request.turn_id},
            }

    async def _do_persist_turn(self, state: ConversationState, runtime: Dict[str, Any], request, review, summary) -> Dict[str, Any]:
        self.store.save_thread(
            {
                "conversation_id": request.conversation_id,
                "owner_id": request.owner_id,
                "owner_type": request.owner_type,
                "session_id": request.session_id,
                "connection_id": request.connection_id,
                "latest_turn_id": request.turn_id,
                "latest_mode": request.mode,
                "graph_run_id": request.graph_run_id,
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "updated_at": utc_now_iso(),
            }
        )
        self.store.save_turn(
            {
                "conversation_id": request.conversation_id,
                "turn_id": request.turn_id,
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "graph_run_id": request.graph_run_id,
                "correlation_id": request.correlation_id,
                "owner_id": request.owner_id,
                "owner_type": request.owner_type,
                "mode": request.mode,
                "user_message": request.user_message,
                "final_answer": state.get("draft_answer", {}).get("text", ""),
                "retrieved_chunks": state.get("retrieved_chunks", []),
                "review_id": review.get("review_id"),
                "created_at": utc_now_iso(),
            }
        )
        self.store.save_summary(
            {
                "conversation_id": request.conversation_id,
                "graph_run_id": request.graph_run_id,
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "owner_id": request.owner_id,
                "owner_type": request.owner_type,
                "summary": summary,
                "updated_at": utc_now_iso(),
            }
        )
        if review:
            self.store.save_answer_review(
                {
                    **review,
                    "conversation_id": request.conversation_id,
                    "turn_id": request.turn_id,
                    "request_id": request.request_id,
                    "trace_id": request.trace_id,
                    "graph_run_id": request.graph_run_id,
                    "correlation_id": request.correlation_id,
                    "owner_id": request.owner_id,
                    "owner_type": request.owner_type,
                }
            )
        snapshot = copy.deepcopy(state)
        snapshot["short_term_summary"] = summary
        self._save_checkpoint(request, snapshot, "persist_turn", "after_persistence", "persisted")
        self.backend_client.publish_answer_generated(request, len(state.get("retrieved_chunks", [])))
        self.backend_client.publish_answer_evaluated(request, review.get("verdict", "unknown"))
        self.logger.info(
            "persist_turn success",
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
        )
        return {
            "short_term_summary": summary,
            "_meta": {"message": "Turn persisted", "debug_excerpt": request.turn_id},
        }

    async def _stream_done(self, state: ConversationState, runtime: Dict[str, Any]) -> Dict[str, Any]:
        emitter: BaseConversationEmitter = runtime["emitter"]
        await emitter.emit(
            "done",
            {
                "final_answer": state.get("draft_answer", {}).get("text", ""),
                "sources": state.get("retrieved_chunks", []),
                "review_summary": self._public_review(state.get("answer_review", {})),
                "retrieval_summary": {
                    "chunk_count": len(state.get("retrieved_chunks", [])),
                    "plan": state.get("retrieval_plan", {}),
                },
                "trace_summary": state.get("trace_events", []),
                "safe_debug_payloads": state.get("debug_payloads", {}),
            },
        )
        return {"_meta": {"message": "Done emitted"}}
