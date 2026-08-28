"""WebSocket runtime for direct frontend chat in the `rag` service."""
from __future__ import annotations

from typing import Any, Dict
import time
from uuid import uuid4

from shared.errors import ValidationError as ValidationException
from app.services.base import BaseRAGService
from app.services.conversation_events import SocketIOConversationEmitter, build_error_event
from app.services.rag_service import RAGService
from shared.auth import AuthIdentity
from shared.context import bound_context


class WebSocketService(BaseRAGService):
    """Track Socket.IO connection metadata and delegate live chat or feedback work."""

    def __init__(self, rag_service: RAGService, logger: Any):
        super().__init__(rag_service.config, logger)
        self.rag_service = rag_service
        self._connections: Dict[str, Dict[str, Any]] = {}

    def register_connection(self, sid: str, identity: AuthIdentity) -> Dict[str, Any]:
        """Register a socket connection and return connection metadata."""
        record = {
            "connection_id": str(uuid4()),
            "session_id": identity.session_id or str(uuid4()),
            "identity": identity,
            "connected_at": time.time(),
        }
        self._connections[sid] = record
        return record

    def unregister_connection(self, sid: str) -> None:
        """Remove socket connection metadata."""
        self._connections.pop(sid, None)

    def _connection_meta(self, sid: str) -> Dict[str, Any]:
        record = self._connections.get(sid)
        if record is None:
            raise ValidationException("Socket is not authenticated")
        if time.time() - record["connected_at"] > self.rag_service.config.socket_connection_ttl_seconds:
            self.unregister_connection(sid)
            raise ValidationException("Socket authentication expired")
        return record

    def build_socket_request(self, sid: str, data: Dict[str, Any]):
        """Build a normalized request enriched with socket-scoped session metadata."""
        meta = self._connection_meta(sid)
        with bound_context(**meta["identity"].to_dict()):
            return self.rag_service.build_request(
                data,
                session_id=meta["session_id"],
                connection_id=meta["connection_id"],
            )

    def build_error_event(
        self,
        sid: str,
        data: Dict[str, Any],
        *,
        code: str,
        failed_node: str,
        retryable: bool,
        message: str,
        details: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Build the standardized error envelope used before graph execution starts."""
        request = self.build_socket_request(sid, data or {})
        return build_error_event(
            request,
            code=code,
            failed_node=failed_node,
            retryable=retryable,
            message=message,
            origin_service="rag",
            origin_location="websocket_service:handle_question",
            details=details,
        )

    async def handle_question(self, sid: str, data: Dict[str, Any], sio: Any) -> Dict[str, Any]:
        """Validate a live question payload and run it through the conversation graph."""
        question = (data.get("question") or "").strip()
        if not question:
            raise ValidationException("Question is required")

        meta = self._connection_meta(sid)
        with bound_context(**meta["identity"].to_dict()):
            request = self.build_socket_request(sid, data)
            emitter = SocketIOConversationEmitter(request, sio, sid)
            self.logger.log(
                "websocket_service:handle_question",
                "Processing chat request",
                {
                    "sid": sid,
                    "conversation_id": request.conversation_id,
                    "turn_id": request.turn_id,
                    "request_id": request.request_id,
                    "mode": request.mode,
                },
            )
            return await self.rag_service.graph_runner.run(
                request,
                emitter,
                resume=bool(data.get("resume", False)),
            )

    async def handle_feedback(self, sid: str, feedback_type: str, data: Dict[str, Any], sio: Any) -> Dict[str, Any]:
        """Persist live feedback and acknowledge it with a standard trace event."""
        meta = self._connection_meta(sid)
        with bound_context(**meta["identity"].to_dict()):
            request = self.build_socket_request(
            sid,
            {
                "question": data.get("question", ""),
                "conversation_id": data.get("conversation_id"),
                "turn_id": data.get("turn_id"),
                "request_id": data.get("request_id"),
                "trace_id": data.get("trace_id"),
                "graph_run_id": data.get("graph_run_id"),
                "correlation_id": data.get("correlation_id"),
                "mode": data.get("mode"),
                "answer_mode": data.get("answer_mode"),
            }
            )
            emitter = SocketIOConversationEmitter(request, sio, sid)
            result = await self.rag_service.handle_feedback(
                feedback_type,
                {
                    **data,
                    "session_id": request.session_id,
                    "connection_id": request.connection_id,
                },
                request=request,
            )
            await emitter.emit(
                "trace",
                {
                    "node": "feedback",
                    "event": "received",
                    "decision": result.get("memory_signal") or "stored",
                    "counters": {"stored": 1},
                    "latency": 0.0,
                },
            )
            return result
