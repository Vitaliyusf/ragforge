"""RabbitMQ backend client for memory, embedding, vector_db, and llm_agent."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from app.core.config import RAGConfig
from app.messaging.rpc_client import RabbitMQRPCClient
from app.services.conversation_messages import (
    base_llm_metadata,
    build_message_envelope,
    chunk_passages,
    conversation_history,
    extract_reply_payload,
    extract_stream_event,
)
from app.services.conversation_types import ConversationRequest
from shared.metrics import METRICS, traffic_class


class ConversationBackendClient:
    """RabbitMQ RPC calls for the complete RAG conversation graph."""

    def __init__(
        self,
        config: RAGConfig,
        service_client: RabbitMQRPCClient,
    ) -> None:
        self.config = config
        self.service_client = service_client

    # ------------------------------------------------------------------
    # Private payload builders
    # ------------------------------------------------------------------

    def _llm_query_rewrite_payload(
        self,
        request: ConversationRequest,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the typed llm-agent payload for query rewriting."""
        recent_messages = conversation_history(context.get("recent_messages"))
        rewrite_goal = (
            f"Rewrite the user query for {request.mode} retrieval in rag. "
            "Use the conversation summary, recent messages, and memory hits when they help retrieval precision. "
            "Prefer one best rewrite."
        )
        return {
            "request_type": "query_rewrite",
            "model": request.model,
            "metadata": base_llm_metadata(request),
            "debug": {"include_visible_reasoning_steps": bool(request.debug)},
            "input": {
                "query": request.user_message,
                "conversation_history": recent_messages or None,
                "rewrite_goal": rewrite_goal,
            },
        }

    def _embedding_query_payload(
        self,
        request: ConversationRequest,
        query: str,
    ) -> Dict[str, Any]:
        """Build the current legacy embedding request for query vectors."""
        return {
            "action": "embed",
            "text": query,
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "request_id": request.request_id,
            "trace_id": request.trace_id,
            "graph_run_id": request.graph_run_id,
        }

    def _llm_risk_scan_payload(
        self,
        request: ConversationRequest,
        text: str,
        stage: str,
    ) -> Dict[str, Any]:
        """Build the typed llm-agent payload for content risk scanning."""
        content_type = "user_input" if stage == "input" else "assistant_output"
        policy_hints = (
            ["prompt_injection", "unsafe_output"] if stage == "output" else ["prompt_injection"]
        )
        return {
            "request_type": "content_risk_scan",
            "model": request.model,
            "metadata": base_llm_metadata(request, stage=stage),
            "debug": {"include_visible_reasoning_steps": bool(request.debug)},
            "input": {
                "content": text,
                "policy_hints": policy_hints,
                "content_type": content_type,
            },
        }

    def _llm_answer_evaluation_payload(
        self,
        request: ConversationRequest,
        answer: str,
        retrieved_chunks: Any,
        mode: str,
    ) -> Dict[str, Any]:
        """Build the typed llm-agent payload for answer evaluation.

        ``reference_context`` carries passage ids so the judge can name the
        passages supporting each claim in the same namespace the answer's
        citation markers resolve to.
        """
        return {
            "request_type": "answer_evaluation",
            "model": request.model,
            "metadata": base_llm_metadata(request, mode=mode),
            "debug": {"include_visible_reasoning_steps": bool(request.debug)},
            "input": {
                "question": request.user_message,
                "answer": answer,
                "reference_context": chunk_passages(retrieved_chunks),
            },
        }

    def _llm_answer_generation_payload(
        self,
        request: ConversationRequest,
        prompt: Dict[str, Any],
        stream_request_id: str,
    ) -> Dict[str, Any]:
        """Build the typed llm-agent payload for answer generation."""
        recent_messages = conversation_history(prompt.get("recent_messages"))
        return {
            "request_type": "answer_generation",
            "model": request.model,
            "metadata": base_llm_metadata(
                request,
                request_id=stream_request_id,
                generation_mode=request.mode,
                revision_attempted=prompt.get("revision_attempted"),
            ),
            "debug": {"include_visible_reasoning_steps": bool(request.debug)},
            "input": {
                "question": request.user_message,
                "retrieved_context": prompt.get("retrieved_context", []),
                "conversation_history": recent_messages or None,
                "instructions": prompt.get("instructions"),
            },
        }

    # ------------------------------------------------------------------
    # Core request dispatcher
    # ------------------------------------------------------------------

    async def _send_request(
        self,
        *,
        routing_key: str,
        target_service: str,
        action: str,
        payload: Dict[str, Any],
        request: ConversationRequest,
        message_type: str = "query",
        request_id_override: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        envelope = build_message_envelope(
            message_type=message_type,
            action=action,
            source_service="rag",
            target_service=target_service,
            request_id=request_id_override or request.request_id,
            trace_id=request.trace_id,
            correlation_id=request.correlation_id,
            payload=payload,
            traffic_class=traffic_class(),
        )
        started = time.monotonic()
        try:
            reply = await self.service_client.request(
                routing_key,
                envelope,
                timeout if timeout is not None else self.config.internal_request_timeout,
            )
        finally:
            # try/finally so a timed-out or failed RPC is measured too, not just
            # the calls that happened to succeed.
            METRICS.rpc_roundtrip_seconds.labels(
                service="rag",
                downstream=target_service,
                traffic_class=traffic_class(),
            ).observe(time.monotonic() - started)
        return extract_reply_payload(reply)

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def resolve_file_labels(
        self,
        request: ConversationRequest,
        labels: list[str],
    ) -> Dict[str, Any]:
        """Resolve filename labels through Files under the propagated identity."""
        return await self._send_request(
            routing_key=self.config.files_routing_key,
            target_service="files",
            action="resolve_file_labels",
            payload={"labels": labels},
            request=request,
            message_type="query",
            timeout=self.config.internal_request_timeout,
        )

    async def resolve_chunk_labels(
        self,
        request: ConversationRequest,
        items: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Resolve exact expected facts through tenant-scoped Files storage."""
        return await self._send_request(
            routing_key=self.config.files_routing_key,
            target_service="files",
            action="resolve_chunk_labels",
            payload={"items": items},
            request=request,
            message_type="query",
            timeout=self.config.internal_request_timeout,
        )

    async def get_relevant_memories(
        self,
        request: ConversationRequest,
        depth: str,
    ) -> Dict[str, Any]:
        payload = {
            "action": "get_relevant_memories",
            "owner_id": request.owner_id,
            "owner_type": request.owner_type,
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "request_id": request.request_id,
            "trace_id": request.trace_id,
            "graph_run_id": request.graph_run_id,
            "query": request.user_message,
            "depth": depth,
        }
        return await self._send_request(
            routing_key=self.config.memory_routing_key,
            target_service="memory",
            action="get_relevant_memories",
            payload=payload,
            request=request,
            message_type="query",
            timeout=self.config.internal_request_timeout,
        )

    async def search_chunks(
        self,
        request: ConversationRequest,
        query: str,
        retrieval_plan: Optional[Dict[str, Any]] = None,
        pass_name: str = "pass_one",
        *,
        top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Embed the query and search the vector store for chunks.

        Args:
            top_k: How many candidates to ask for. Defaults to
                ``config.top_k_documents`` — the production answer-context
                depth every conversation-graph caller wants. It is overridden
                only by the retrieval eval, which must retrieve at least as
                many candidates as the largest k it reports, and whose depth
                is therefore a property of the measurement rather than of the
                application being measured.
        """
        embedding_response = await self._send_request(
            routing_key=self.config.embedding_routing_key,
            target_service="embedding",
            action="embed",
            payload=self._embedding_query_payload(request, query),
            request=request,
            message_type="query",
            timeout=self.config.internal_request_timeout,
        )
        query_vector = embedding_response.get("embedding") or []
        if not query_vector:
            raise RuntimeError("Embedding query returned no query_vector")

        payload = {
            "query_vector": query_vector,
            "top_k": self.config.top_k_documents if top_k is None else top_k,
            "filters": {},
            "include_payload": True,
            "include_vector": False,
            "query": query,
            "pass_name": pass_name,
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "request_id": request.request_id,
            "trace_id": request.trace_id,
            "graph_run_id": request.graph_run_id,
            "retrieval_plan": retrieval_plan or {},
        }
        return await self._send_request(
            routing_key=self.config.vector_db_routing_key,
            target_service="vector_db",
            action="search_chunks",
            payload=payload,
            request=request,
            message_type="query",
            timeout=self.config.internal_request_timeout,
        )

    async def verify_label_ids(
        self,
        request: ConversationRequest,
        chunk_ids: Optional[list] = None,
        file_ids: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Ask vector_db which golden-set label ids still exist.

        Read-only and used only by the eval harness. No filter is sent: the
        vector service scopes the lookup from the identity the envelope is
        signed with, so this call can only ever report on the caller's own
        tenant. Nothing here touches the retrieval path — a run that skips
        validation retrieves exactly as it did before.

        Args:
            request: Carries the ids the envelope is traced with.
            chunk_ids: Labelled chunk ids to check.
            file_ids: Labelled file ids to check.

        Returns:
            The vector_db reply body: ``chunk_ids`` and ``file_ids``, each
            with ``present``, ``retrievable`` and ``missing``.
        """
        payload = {
            "chunk_ids": list(chunk_ids or []),
            "file_ids": list(file_ids or []),
            "request_id": request.request_id,
            "trace_id": request.trace_id,
        }
        return await self._send_request(
            routing_key=self.config.vector_db_routing_key,
            target_service="vector_db",
            action="verify_chunk_ids",
            payload=payload,
            request=request,
            message_type="query",
            timeout=self.config.internal_request_timeout,
        )

    async def query_rewrite(
        self,
        request: ConversationRequest,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = self._llm_query_rewrite_payload(request, context)
        return await self._send_request(
            routing_key=self.config.llm_agent_routing_key,
            target_service="llm_agent",
            action="query_rewrite",
            payload=payload,
            request=request,
            message_type="query",
            timeout=self.config.internal_request_timeout,
        )

    async def risk_scan(
        self,
        request: ConversationRequest,
        text: str,
        stage: str,
    ) -> Dict[str, Any]:
        payload = self._llm_risk_scan_payload(request, text, stage)
        return await self._send_request(
            routing_key=self.config.llm_agent_routing_key,
            target_service="llm_agent",
            action="content_risk_scan",
            payload=payload,
            request=request,
            message_type="query",
            timeout=self.config.internal_request_timeout,
        )

    async def evaluate_answer(
        self,
        request: ConversationRequest,
        answer: str,
        retrieved_chunks: Any,
        mode: str,
    ) -> Dict[str, Any]:
        payload = self._llm_answer_evaluation_payload(request, answer, retrieved_chunks, mode)
        return await self._send_request(
            routing_key=self.config.llm_agent_routing_key,
            target_service="llm_agent",
            action="answer_evaluation",
            payload=payload,
            request=request,
            message_type="query",
            timeout=self.config.evaluation_request_timeout,
        )

    async def generate_answer(
        self,
        request: ConversationRequest,
        prompt: Dict[str, Any],
        stream_request_id: str,
        token_callback,
    ) -> Dict[str, Any]:
        payload = self._llm_answer_generation_payload(request, prompt, stream_request_id)
        envelope = build_message_envelope(
            message_type="command",
            action="answer_generation",
            source_service="rag",
            target_service="llm_agent",
            request_id=stream_request_id,
            trace_id=request.trace_id,
            correlation_id=request.correlation_id,
            payload=payload,
            traffic_class=traffic_class(),
        )
        chunks: list[str] = []
        token_index = 0

        async def _on_stream_event(message: Dict[str, Any]) -> None:
            nonlocal token_index
            event = extract_stream_event(message)
            text_delta = event.get("text_delta", "")
            if text_delta:
                chunks.append(text_delta)
                await token_callback(text_delta, token_index)
                token_index += 1
            if event.get("event") == "error":
                raise RuntimeError(event.get("message") or "llm stream error")

        reply = await self.service_client.request_stream(
            self.config.llm_agent_routing_key,
            envelope,
            self.config.generation_request_timeout,
            _on_stream_event,
        )
        response = extract_reply_payload(reply)
        if not response.get("answer") and chunks:
            response["answer"] = "".join(chunks)
        return response

    # ------------------------------------------------------------------
    # Domain event publishers
    # ------------------------------------------------------------------

    def _schedule_publish(self, routing_key: str, envelope: Dict[str, Any]) -> None:
        """Schedule a non-blocking RabbitMQ publish from the async RAG runtime."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        task = loop.create_task(self.service_client.publish(routing_key, envelope))

        def _consume_result(completed: asyncio.Task[None]) -> None:
            try:
                completed.result()
            except Exception:
                # Domain events must not fail a completed user request. RPC
                # commands that require acknowledgement use _send_request.
                return

        task.add_done_callback(_consume_result)

    def _publish_domain_event(
        self,
        action: str,
        request: ConversationRequest,
        payload: Dict[str, Any],
    ) -> None:
        envelope = build_message_envelope(
            message_type="event",
            action=action,
            source_service="rag",
            target_service="observers",
            request_id=request.request_id,
            trace_id=request.trace_id,
            correlation_id=request.correlation_id,
            payload=payload,
        )
        self._schedule_publish(action, envelope)

    def publish_turn_started(self, request: ConversationRequest) -> None:
        self._publish_domain_event(
            "rag.turn.started",
            request,
            {
                "service": "rag",
                "conversation_id": request.conversation_id,
                "turn_id": request.turn_id,
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "graph_run_id": request.graph_run_id,
                "mode": request.mode,
                "owner_id": request.owner_id,
                "owner_type": request.owner_type,
            },
        )

    def publish_answer_generated(self, request: ConversationRequest, chunk_count: int) -> None:
        self._publish_domain_event(
            "rag.answer.generated",
            request,
            {
                "service": "rag",
                "conversation_id": request.conversation_id,
                "turn_id": request.turn_id,
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "graph_run_id": request.graph_run_id,
                "mode": request.mode,
                "chunk_count": chunk_count,
            },
        )

    def publish_answer_evaluated(self, request: ConversationRequest, verdict: str) -> None:
        self._publish_domain_event(
            "rag.answer.evaluated",
            request,
            {
                "service": "rag",
                "conversation_id": request.conversation_id,
                "turn_id": request.turn_id,
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "graph_run_id": request.graph_run_id,
                "mode": request.mode,
                "verdict": verdict,
            },
        )

    def publish_feedback_received(self, request: ConversationRequest, feedback_type: str) -> None:
        self._publish_domain_event(
            "rag.feedback.received",
            request,
            {
                "service": "rag",
                "conversation_id": request.conversation_id,
                "turn_id": request.turn_id,
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "graph_run_id": request.graph_run_id,
                "feedback_type": feedback_type,
                "owner_id": request.owner_id,
                "owner_type": request.owner_type,
            },
        )

    def publish_memory_write_requested(self, payload: Dict[str, Any]) -> None:
        request_id = str(payload.get("request_id") or "")
        trace_id = str(payload.get("trace_id") or request_id)
        envelope = build_message_envelope(
            message_type="command",
            action="write_memory",
            source_service="rag",
            target_service="memory",
            request_id=request_id,
            trace_id=trace_id,
            correlation_id=payload.get("correlation_id"),
            payload={
                "candidate": {
                    "content": {"text": str(payload.get("signal") or "Repeated user feedback")},
                    "owner_id": payload.get("owner_id"),
                    "owner_type": payload.get("owner_type"),
                    "source": "rag.feedback",
                    "confidence": 0.8,
                    "importance": 0.7,
                    "tags": ["feedback", str(payload.get("feedback_type") or "interaction")],
                    "provenance": payload,
                }
            },
        )
        self._schedule_publish(self.config.memory_routing_key, envelope)
