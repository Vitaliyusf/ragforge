"""Memory handler service for RabbitMQ-backed requests."""
from __future__ import annotations

import asyncio
import copy
import uuid
from contextvars import copy_context
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.errors import ChatNotFoundError, ServiceException, public_service_error
from app.core.logging_config import ServiceLogger
from app.services.chat_exit_service import ChatExitService
from app.services.chat_service import ChatService
from app.services.memory_service import LongTermMemoryService
from app.services.message_service import MessageService
from app.services.tenant_scope import current_identity


SHARED_ENVELOPE_FIELDS = {
    "message_id",
    "message_type",
    "action",
    "source_service",
    "target_service",
    "request_id",
    "trace_id",
    "correlation_id",
    "reply_to",
    "stream_to",
    "timestamp",
    "payload",
}

QUERY_ACTIONS = {
    "get_relevant_memories",
    "list_memory_for_debug",
    "get_chats",
    "get_messages",
    "get_long_term_memories",
    "get_user_insight",
    "get_compressed_history",
}


class MemoryHandlerService:
    """Handler for memory RabbitMQ contracts plus legacy compatibility actions."""

    def __init__(
        self,
        chat_service: ChatService,
        message_service: MessageService,
        memory_service: LongTermMemoryService,
        chat_exit_service: ChatExitService,
        logger: ServiceLogger,
    ):
        self.chat_service = chat_service
        self.message_service = message_service
        self.memory_service = memory_service
        self.chat_exit_service = chat_exit_service
        self.logger = logger

    def _now_iso(self) -> str:
        """Return the current UTC timestamp."""
        return datetime.now(timezone.utc).isoformat()

    def _infer_service_from_topic(self, topic: Optional[str]) -> str:
        """Infer a service name from a reply topic like rag.replies."""
        if topic and "." in topic:
            return topic.split(".", 1)[0]
        return "unknown"

    def _infer_action(self, topic: str, request: Dict[str, Any]) -> str:
        """Infer action for legacy dedicated topics."""
        action = request.get("action")
        if action:
            return str(action)
        return ""

    def _infer_message_type(self, action: str) -> str:
        """Infer the canonical message type for legacy input."""
        if action in QUERY_ACTIONS or action.startswith("get_") or action.startswith("list_"):
            return "query"
        return "command"

    def _extract_payload(self, request: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
        """Extract canonical payload or derive it from a legacy flat request."""
        payload = request.get("payload")
        if isinstance(payload, dict):
            return copy.deepcopy(payload), False

        legacy_payload = {
            key: copy.deepcopy(value)
            for key, value in request.items()
            if key not in SHARED_ENVELOPE_FIELDS
        }
        return legacy_payload, True

    def _build_envelope_context(
        self,
        topic: str,
        request: Dict[str, Any],
        action: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a normalized shared envelope from canonical or legacy input."""
        resolved_action = action or self._infer_action(topic, request)
        payload, legacy_input = self._extract_payload(request)

        message_id = str(request.get("message_id") or uuid.uuid4())
        correlation_id = str(request.get("correlation_id") or message_id)
        request_id = str(request.get("request_id") or correlation_id)
        trace_id = str(request.get("trace_id") or request_id)
        reply_to = request.get("reply_to")

        source_topic = reply_to or None
        source_service = request.get("source_service") or self._infer_service_from_topic(source_topic)

        return {
            "message_id": message_id,
            "message_type": request.get("message_type") or self._infer_message_type(resolved_action),
            "action": resolved_action,
            "source_service": source_service,
            "target_service": request.get("target_service") or settings.service_name,
            "request_id": request_id,
            "trace_id": trace_id,
            "correlation_id": correlation_id,
            "reply_to": reply_to,
            "stream_to": request.get("stream_to"),
            "timestamp": request.get("timestamp") or self._now_iso(),
            "payload": payload,
            "_legacy_input": legacy_input,
        }

    def _normalize_request(self, topic: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize requests."""
        if not isinstance(request, dict):
            raise ServiceException("Request must be a dict/object")

        normalized_request = self._build_envelope_context(topic, request)
        if not normalized_request["action"]:
            raise ServiceException("action is required")
        return normalized_request

    def _flatten_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten payload fields back onto the request for action handlers."""
        payload = request.get("payload")
        merged = copy.deepcopy(payload) if isinstance(payload, dict) else {}
        merged["message_id"] = copy.deepcopy(request.get("message_id"))
        for key in (
            "message_type",
            "action",
            "source_service",
            "target_service",
            "request_id",
            "trace_id",
            "correlation_id",
            "reply_to",
            "stream_to",
            "timestamp",
            "_legacy_input",
        ):
            merged[key] = copy.deepcopy(request.get(key))
        merged["payload"] = copy.deepcopy(payload) if isinstance(payload, dict) else {}
        identity = current_identity()
        if identity is not None:
            merged["tenant_id"] = identity.tenant_id
            merged["owner_id"] = identity.user_id
            merged["owner_type"] = "user"
            if isinstance(merged.get("candidate"), dict):
                merged["candidate"]["owner_id"] = identity.user_id
                merged["candidate"]["owner_type"] = "user"
            if isinstance(merged.get("query_context"), dict):
                merged["query_context"]["owner_id"] = identity.user_id
                merged["query_context"]["owner_type"] = "user"
        return merged

    def _reply_topic(self, request: Dict[str, Any]) -> Optional[str]:
        """Resolve the reply routing key (reply_to) for the RabbitMQ reply."""
        return request.get("reply_to") or None

    def _target_service(self, request: Dict[str, Any]) -> str:
        """Resolve the intended receiver of replies and completion events."""
        if request.get("source_service"):
            return str(request["source_service"])

        reply_topic = self._reply_topic(request)
        if reply_topic:
            return self._infer_service_from_topic(reply_topic)
        return "unknown"

    def _send_response(self, request: Dict[str, Any], data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build and return a canonical success reply envelope."""
        message = {
            "message_id": str(uuid.uuid4()),
            "message_type": "reply",
            "action": request.get("action") or "unknown",
            "source_service": settings.service_name,
            "target_service": self._target_service(request),
            "request_id": request.get("request_id") or request.get("correlation_id") or str(uuid.uuid4()),
            "trace_id": request.get("trace_id") or request.get("request_id") or str(uuid.uuid4()),
            "correlation_id": request.get("correlation_id") or str(uuid.uuid4()),
            "timestamp": self._now_iso(),
            "success": True,
            "payload": copy.deepcopy(data or {}),
        }
        self.logger.log(
            "handler:send_response",
            "Response built successfully",
            {
                "correlation_id": request.get("correlation_id"),
                "trace_id": request.get("trace_id"),
                "action": request.get("action"),
            },
        )
        return message

    def _send_error(self, request: Dict[str, Any], error: str | Exception) -> Optional[Dict[str, Any]]:
        """Build and return a canonical error reply envelope."""
        error_payload = public_service_error(error)
        message = {
            "message_id": str(uuid.uuid4()),
            "message_type": "reply",
            "action": request.get("action") or "unknown",
            "source_service": settings.service_name,
            "target_service": self._target_service(request),
            "request_id": request.get("request_id") or request.get("correlation_id") or str(uuid.uuid4()),
            "trace_id": request.get("trace_id") or request.get("request_id") or str(uuid.uuid4()),
            "correlation_id": request.get("correlation_id") or str(uuid.uuid4()),
            "timestamp": self._now_iso(),
            "success": False,
            "payload": {},
            "error": error_payload,
        }
        self.logger.log(
            "handler:send_error",
            "Error response built",
            {
                "correlation_id": request.get("correlation_id"),
                "trace_id": request.get("trace_id"),
                "action": request.get("action"),
                "error": error_payload["message"],
            },
        )
        return message

    def _publish_write_completed(
        self,
        request: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Log that a write_memory operation completed (no-op in RabbitMQ mode)."""
        self.logger.log(
            "handler:write_completed",
            "Memory write completed",
            {
                "request_id": request.get("request_id"),
                "correlation_id": request.get("correlation_id"),
                "status": result.get("status"),
                "memory_id": result.get("memory_id"),
            },
        )

    def _memory_request_context(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Build service request context for write operations."""
        return {
            "request_id": request.get("request_id"),
            "trace_id": request.get("trace_id"),
            "correlation_id": request.get("correlation_id"),
            "owner_id": request.get("owner_id"),
            "owner_type": request.get("owner_type"),
            "tenant_id": request.get("tenant_id"),
            "source": request.get("source") or request.get("source_service") or request.get("action") or "rabbitmq_request",
        }

    def process_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process action-based requests from the memory queue. Returns reply dict."""
        raw_request = request if isinstance(request, dict) else {}
        action = raw_request.get("action", "")
        normalized_request: Optional[Dict[str, Any]] = None

        try:
            normalized_request = self._normalize_request(settings.rabbitmq_queue, raw_request)
            request = self._flatten_request(normalized_request)
            action = request.get("action", "")

            self.logger.log(
                "handler:process_request",
                f"Processing {action} request",
                {
                    "correlation_id": request.get("correlation_id"),
                    "trace_id": request.get("trace_id"),
                    "action": action,
                    "reply_to": self._reply_topic(request),
                    "message_type": request.get("message_type"),
                },
            )

            if action == "write_memory":
                return self._handle_write_memory(request)
            elif action == "get_relevant_memories":
                return self._handle_get_relevant_memories(request)
            elif action == "list_memory_for_debug":
                return self._handle_list_memory_for_debug(request)
            elif action == "create_chat":
                return self._handle_create_chat(request)
            elif action == "add_message":
                return self._handle_add_message(request)
            elif action == "get_chats":
                return self._handle_get_chats(request)
            elif action == "get_messages":
                return self._handle_get_messages(request)
            elif action == "delete_chat":
                return self._handle_delete_chat(request)
            elif action == "process_chat_exit":
                return self._handle_process_chat_exit(request)
            elif action == "generate_title":
                return self._handle_generate_title(request)
            elif action == "update_chat_title":
                return self._handle_update_chat_title(request)
            elif action == "get_long_term_memories":
                return self._handle_get_long_term_memories(request)
            elif action == "create_long_term_memory":
                return self._handle_create_long_term_memory(request)
            elif action == "update_long_term_memory":
                return self._handle_update_long_term_memory(request)
            elif action == "delete_long_term_memory":
                return self._handle_delete_long_term_memory(request)
            elif action == "get_user_insight":
                return self._handle_get_user_insight(request)
            elif action == "update_user_insight":
                return self._handle_update_user_insight(request)
            elif action == "get_compressed_history":
                return self._handle_get_compressed_history(request)
            else:
                raise ServiceException(f"Unknown action: {action}")
        except Exception as exc:
            error_request = self._flatten_request(
                normalized_request or self._build_envelope_context(settings.rabbitmq_queue, raw_request, action=action)
            )
            self.logger.log(
                "handler:process_request",
                "Error processing request",
                {
                    "correlation_id": error_request.get("correlation_id"),
                    "trace_id": error_request.get("trace_id"),
                    "action": error_request.get("action"),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                "E",
            )
            return self._send_error(error_request, exc)

    def process_write_requested(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process write_memory commands. Returns reply dict."""
        raw_request = request if isinstance(request, dict) else {}
        normalized_request: Optional[Dict[str, Any]] = None

        try:
            normalized_request = self._normalize_request(settings.rabbitmq_queue, raw_request)
            request = self._flatten_request(normalized_request)

            self.logger.log(
                "handler:process_write_requested",
                "Processing write_memory request",
                {
                    "request_id": request.get("request_id"),
                    "correlation_id": request.get("correlation_id"),
                    "trace_id": request.get("trace_id"),
                    "owner_id": request.get("owner_id"),
                    "reply_to": self._reply_topic(request),
                },
            )

            result = self.memory_service.write_memory(
                request.get("candidate") or {},
                self._memory_request_context(request),
            )
            self._publish_write_completed(request, result)
            return self._send_response(request, result)
        except Exception as exc:
            error_request = self._flatten_request(
                normalized_request
                or self._build_envelope_context(
                    settings.rabbitmq_queue,
                    raw_request,
                    action="write_memory",
                )
            )
            failure = {
                "status": "failed",
                "memory_id": None,
                "memory_class": None,
                "reason": str(exc),
                "qdrant_indexed": None,
            }
            self._publish_write_completed(error_request, failure)
            return self._send_error(error_request, exc)

    def _handle_write_memory(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle write_memory action."""
        result = self.memory_service.write_memory(
            request.get("candidate") or {},
            self._memory_request_context(request),
        )
        return self._send_response(request, result)

    def _handle_get_relevant_memories(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle get_relevant_memories action."""
        query_context = dict(request.get("query_context") or {})
        query_context.setdefault("owner_id", request.get("owner_id"))
        query_context.setdefault("owner_type", request.get("owner_type"))
        if "limit" in request and "limit" not in query_context:
            query_context["limit"] = request["limit"]
        if "memory_classes" in request and "memory_classes" not in query_context:
            query_context["memory_classes"] = request["memory_classes"]
        result = self.memory_service.get_relevant_memories(query_context)
        return self._send_response(request, result)

    def _handle_list_memory_for_debug(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle list_memory_for_debug action."""
        filters = dict(request.get("payload") or {})
        result = self.memory_service.list_memory_for_debug(filters)
        return self._send_response(request, result)

    def _handle_create_chat(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle create_chat action."""
        chat_id = request.get("chat_id")
        title = request.get("title", "New Chat")
        if not chat_id:
            return self._send_error(request, "chat_id is required")
        chat = self.chat_service.create_chat(chat_id, title)
        return self._send_response(request, {"status": "success", "chat_id": chat["id"]})

    def _handle_add_message(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle add_message action."""
        chat_id = request.get("chat_id")
        message_id = request.get("message_id")
        sender = request.get("sender", "User")
        message_text = request.get("message", "")
        if not chat_id or not message_id:
            return self._send_error(request, "chat_id and message_id are required")
        message = self.message_service.add_message(message_id, chat_id, sender, message_text)
        return self._send_response(request, {"status": "success", "message_id": message["id"]})

    def _handle_get_chats(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle get_chats action."""
        chats = self.chat_service.get_all_chats()
        return self._send_response(request, {"status": "success", "chats": chats})

    def _handle_get_messages(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle get_messages action."""
        chat_id = request.get("chat_id")
        if not chat_id:
            return self._send_error(request, "chat_id is required")
        messages = self.message_service.get_messages(chat_id)
        return self._send_response(request, {"status": "success", "messages": messages})

    def _handle_delete_chat(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle delete_chat action.

        Deleting the chat itself is the user's goal, so ancillary cleanup
        (long-term memories, messages) is best-effort: a failure there — for
        example an unavailable Qdrant index backend — must not abort the whole
        request and leave the chat undeletable. The chat delete is also
        idempotent: a chat that is already gone counts as a successful delete.
        """
        chat_id = request.get("chat_id")
        if not chat_id:
            return self._send_error(request, "chat_id is required")

        memories_deleted = 0
        try:
            memories_deleted = self.memory_service.delete_memories_by_chat_id(chat_id)
        except Exception as exc:
            self.logger.log(
                "handler:delete_chat",
                "Memory cleanup failed; continuing with chat deletion",
                {"chat_id": chat_id, "error": str(exc)},
                "E",
            )

        try:
            self.message_service.delete_messages_by_chat(chat_id)
        except Exception as exc:
            self.logger.log(
                "handler:delete_chat",
                "Message cleanup failed; continuing with chat deletion",
                {"chat_id": chat_id, "error": str(exc)},
                "E",
            )

        try:
            self.chat_service.delete_chat(chat_id)
        except ChatNotFoundError:
            self.logger.log(
                "handler:delete_chat",
                "Chat already absent; treating delete as successful",
                {"chat_id": chat_id},
            )

        return self._send_response(
            request,
            {"status": "success", "message": "Chat deleted", "memories_deleted": memories_deleted},
        )

    def _handle_process_chat_exit(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle process_chat_exit action."""
        chat_id = request.get("chat_id")
        if not chat_id:
            return self._send_error(request, "chat_id is required")
        result = self.chat_exit_service.process_chat_exit(chat_id)
        return self._send_response(request, result)

    def _handle_generate_title(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle generate_title action — idempotently name an untitled chat."""
        chat_id = request.get("chat_id")
        if not chat_id:
            return self._send_error(request, "chat_id is required")
        result = self.chat_exit_service.generate_title(chat_id)
        return self._send_response(request, result)

    def _handle_update_chat_title(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle update_chat_title action."""
        chat_id = request.get("chat_id")
        title = request.get("title")
        if not chat_id or not title:
            return self._send_error(request, "chat_id and title are required")
        success = self.chat_service.update_title(chat_id, title)
        if not success:
            return self._send_error(request, "Failed to update chat title")
        return self._send_response(request, {"status": "success", "message": "Chat title updated"})

    def _handle_get_long_term_memories(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle get_long_term_memories action."""
        memories = self.memory_service.get_all_memories()
        return self._send_response(request, {"status": "success", "memories": memories})

    def _handle_create_long_term_memory(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle create_long_term_memory action."""
        content = request.get("content")
        category = request.get("category")
        metadata = request.get("metadata")
        if not content:
            return self._send_error(request, "content is required")
        memory = self.memory_service.create_memory(content, category, metadata)
        return self._send_response(request, {"status": "success", "memory": memory})

    def _handle_update_long_term_memory(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle update_long_term_memory action."""
        memory_id = request.get("memory_id")
        if not memory_id:
            return self._send_error(request, "memory_id is required")
        memory = self.memory_service.update_memory(
            memory_id,
            request.get("content"),
            request.get("category"),
            request.get("metadata"),
        )
        return self._send_response(request, {"status": "success", "memory": memory})

    def _handle_delete_long_term_memory(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle delete_long_term_memory action."""
        memory_id = request.get("memory_id")
        if not memory_id:
            return self._send_error(request, "memory_id is required")
        self.memory_service.delete_memory(memory_id)
        return self._send_response(request, {"status": "success", "message": "Memory deleted"})

    def _handle_get_user_insight(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle get_user_insight action."""
        insight = self.memory_service.get_user_insight()
        return self._send_response(
            request,
            {"status": "success", "insight": insight.get("content", "") if insight else ""},
        )

    def _handle_update_user_insight(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle update_user_insight action."""
        insight = request.get("insight")
        if not insight:
            return self._send_error(request, "insight is required")
        result = self.memory_service.update_user_insight(insight)
        return self._send_response(request, {"status": "success", "insight": result.get("content", "")})

    def _handle_get_compressed_history(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return compressed_summary plus recent raw messages for a chat."""
        chat_id = request.get("chat_id")
        recent_count = int(request.get("recent_count", 3))
        if not chat_id:
            return self._send_error(request, "chat_id is required")
        summary = self.chat_service.get_compressed_summary(chat_id)
        all_messages = self.message_service.get_messages(chat_id)
        recent_messages = all_messages[-recent_count:] if all_messages else []
        return self._send_response(
            request,
            {
                "status": "success",
                "compressed_summary": summary,
                "recent_messages": recent_messages,
            },
        )

    async def process_request_async(
        self,
        body: Dict[str, Any],
        reply_to: str,
        correlation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Async entry point for RabbitMQ consumer. Returns reply dict."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            copy_context().run,
            self._process_and_build_reply,
            body,
            reply_to,
            correlation_id,
        )

    def _process_and_build_reply(
        self,
        body: Dict[str, Any],
        reply_to: str,
        correlation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Synchronous processing — returns reply dict."""
        body = dict(body)  # shallow copy to avoid mutating the caller's dict
        body.setdefault("reply_to", reply_to)
        body.setdefault("correlation_id", correlation_id)
        return self.process_request(body)
