"""Main orchestrator facade for the LangGraph-backed `rag` service."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from uuid import uuid4

from app.core.config import RAGConfig
from app.services.base import BaseRAGService
from app.services.conversation_events import CollectingConversationEmitter
from app.services.conversation_graph import ConversationGraphRunner
from app.services.conversation_backend_client import ConversationBackendClient
from app.services.conversation_persistence import BaseConversationStore
from app.services.conversation_tracing import ConversationTracer
from app.services.conversation_types import ConversationRequest, normalize_mode, utc_now_iso
from shared.auth import identity_from_context


class RAGService(BaseRAGService):
    """Normalize external inputs and delegate chat or feedback work into the runtime."""

    def __init__(
        self,
        backend_client: ConversationBackendClient,
        conversation_store: BaseConversationStore,
        logger: Any,
        config: RAGConfig,
        tracer: Optional[ConversationTracer] = None,
    ):
        super().__init__(config, logger)
        self.backend_client = backend_client
        self.conversation_store = conversation_store
        self.tracer = tracer or ConversationTracer(config)
        self.graph_runner = ConversationGraphRunner(
            config=config,
            backend_client=backend_client,
            store=conversation_store,
            tracer=self.tracer,
            logger=logger,
        )

    def build_request(
        self,
        data: Dict[str, Any],
        *,
        session_id: Optional[str] = None,
        connection_id: Optional[str] = None,
    ) -> ConversationRequest:
        """Build a normalized request object from HTTP, Socket.IO, or RabbitMQ input."""
        mode = normalize_mode(data.get("mode"), data.get("answer_mode"))
        identity = identity_from_context()
        return ConversationRequest(
            user_message=data.get("question", "").strip(),
            mode=mode,
            model=data.get("model"),
            conversation_id=data.get("conversation_id") or str(uuid4()),
            turn_id=data.get("turn_id") or str(uuid4()),
            request_id=data.get("request_id") or str(uuid4()),
            trace_id=data.get("trace_id") or str(uuid4()),
            graph_run_id=data.get("graph_run_id") or str(uuid4()),
            correlation_id=data.get("correlation_id"),
            owner_id=identity.user_id,
            owner_type="user",
            session_id=data.get("session_id") or session_id,
            connection_id=data.get("connection_id") or connection_id,
            history=data.get("history"),
            raw_mode=data.get("mode") or data.get("answer_mode"),
            debug=identity.role == "admin" and bool(data.get("debug", True)),
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            role=identity.role,
            admin_id=identity.admin_id,
        )

    async def handle_chat_request(
        self,
        data: Dict[str, Any],
        emitter,
        *,
        session_id: Optional[str] = None,
        connection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run one chat request through the conversation graph and emit progress events."""
        request = self.build_request(data, session_id=session_id, connection_id=connection_id)
        self.logger.log(
            "rag_service:handle_chat_request",
            "Handling conversation request",
            {
                "conversation_id": request.conversation_id,
                "turn_id": request.turn_id,
                "request_id": request.request_id,
                "mode": request.mode,
            },
        )
        return await self.graph_runner.run(
            request,
            emitter,
            resume=bool(data.get("resume", False)),
        )

    async def query(
        self,
        question: str,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        answer_mode: Optional[str] = None,
        history: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the secondary HTTP query helper and return the compact HTTP response payload."""
        request = self.build_request(
            {
                "question": question,
                "model": model,
                "mode": mode,
                "answer_mode": answer_mode,
                "history": history,
            }
        )
        emitter = CollectingConversationEmitter(request)
        result = await self.graph_runner.run(request, emitter)
        return {
            "answer": result.get("answer", ""),
            "sources": [item.get("text", "") for item in result.get("sources", [])],
            "review": result.get("review", {}),
            "trace_events": result.get("trace_events", []),
            "debug_payloads": result.get("debug_payloads", {}),
        }

    def process_rag_query(
        self,
        question: str,
        model: Optional[str] = None,
        answer_mode: str = "quick",
        history: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the query helper synchronously for legacy code paths that cannot await."""
        return asyncio.run(
            self.query(
                question=question,
                model=model,
                answer_mode=answer_mode,
                history=history,
            )
        )

    async def handle_feedback(
        self,
        feedback_type: str,
        payload: Dict[str, Any],
        request: Optional[ConversationRequest] = None,
    ) -> Dict[str, Any]:
        """Persist feedback and publish a memory-write request once the signal threshold is met."""
        request = request or self.build_request(payload)
        signal = self._normalize_feedback_signal(payload)
        document = {
            "conversation_id": request.conversation_id,
            "turn_id": request.turn_id,
            "request_id": request.request_id,
            "trace_id": request.trace_id,
            "graph_run_id": request.graph_run_id,
            "correlation_id": request.correlation_id,
            "owner_id": request.owner_id,
            "owner_type": request.owner_type,
            "owner_key": request.owner_key(),
            "session_id": request.session_id,
            "connection_id": request.connection_id,
            "mode": request.mode,
            "feedback_type": feedback_type,
            "memory_signal": signal,
            "payload": payload,
            "created_at": utc_now_iso(),
            "tenant_id": request.tenant_id,
            "owner_user_id": request.user_id,
            "owner_admin_id": request.admin_id or request.user_id,
        }
        collection = (
            self.config.user_feedback_collection
            if feedback_type == "answer_feedback"
            else self.config.flow_feedback_collection
        )
        self.conversation_store.save_feedback(collection, document)
        self.backend_client.publish_feedback_received(request, feedback_type)

        if signal:
            count = self.conversation_store.count_feedback_signals(request.owner_key(), signal)
            if count == self.config.feedback_memory_threshold:
                evidence = self.conversation_store.list_feedback_documents(
                    request.owner_key(),
                    signal,
                    self.config.feedback_memory_threshold,
                )
                supporting_turn_ids = list(dict.fromkeys(item.get("turn_id") for item in evidence if item.get("turn_id")))
                supporting_request_ids = list(dict.fromkeys(item.get("request_id") for item in evidence if item.get("request_id")))
                supporting_feedback_types = list(
                    dict.fromkeys(item.get("feedback_type") for item in evidence if item.get("feedback_type"))
                )
                self.backend_client.publish_memory_write_requested(
                    {
                        "service": "rag",
                        "source": "rag.feedback",
                        "owner_id": request.owner_id,
                        "owner_type": request.owner_type,
                        "owner_key": request.owner_key(),
                        "signal": signal,
                        "conversation_id": request.conversation_id,
                        "turn_id": request.turn_id,
                        "request_id": request.request_id,
                        "trace_id": request.trace_id,
                        "graph_run_id": request.graph_run_id,
                        "threshold": self.config.feedback_memory_threshold,
                        "supporting_turn_ids": supporting_turn_ids,
                        "supporting_request_ids": supporting_request_ids,
                        "supporting_feedback_types": supporting_feedback_types,
                    }
                )

        return {
            "stored": True,
            "feedback_type": feedback_type,
            "memory_signal": signal,
        }

    def _normalize_feedback_signal(self, payload: Dict[str, Any]) -> Optional[str]:
        """Map feedback text into the stable preference keys used for memory aggregation."""
        text = " ".join(
            str(item or "")
            for item in [
                payload.get("comment"),
                payload.get("label"),
                payload.get("rating"),
                payload.get("category"),
            ]
        ).lower()
        if not text.strip():
            return None
        if any(term in text for term in ["concise", "short", "brief"]):
            return "user_prefers_concise_answers"
        if any(term in text for term in ["extended", "detailed", "thorough", "depth"]):
            return "user_prefers_extended_answers"
        if any(term in text for term in ["citation", "source", "reference"]):
            return "user_prefers_citations"
        if any(term in text for term in ["step-by-step", "step by step", "steps"]):
            return "user_prefers_step_by_step_answers"
        return None
