"""ASGI entrypoint for the `rag` HTTP, Socket.IO, and RabbitMQ runtime."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

import socketio
from fastapi import FastAPI

try:
    from shared.metrics import setup_metrics
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

from app.core.config import RAGConfig
from app.core.exception_handlers import register_exception_handlers
from app.core.logging_config import ServiceLogger
from app.messaging.factories import MessageQueueFactory
from app.messaging.rag_rpc_handler import build_reply_envelope, extract_request_payload
from app.messaging.rpc_client import RabbitMQRPCClient
from app.rest.routes import api_router
from app.rest.v1.rag import get_rag_service
from app.services.conversation_backend_client import ConversationBackendClient
from app.services.conversation_persistence import create_conversation_store
from app.services.conversation_tracing import ConversationTracer
from app.services.eval_runner import EVAL_ACTIONS, create_eval_runner
from app.services.eval_store import create_eval_store
from app.services.metrics_query import METRICS_ACTION, MetricsQueryService
from app.services.rag_service import RAGService
from app.services.websocket_service import WebSocketService
from app.utils.common import setup_cors
from shared.auth import AuthError, verify_auth_ticket

# ---------------------------------------------------------------------------
# Module-level singletons (initialised at import time for hot-reload support)
# ---------------------------------------------------------------------------

config = RAGConfig()
logger = ServiceLogger(config.service_name)
conversation_store = create_conversation_store(config)
rpc_client = RabbitMQRPCClient(config)
backend_client = ConversationBackendClient(config, rpc_client)
tracer = ConversationTracer(config)
rag_service = RAGService(
    backend_client=backend_client,
    conversation_store=conversation_store,
    logger=logger,
    config=config,
    tracer=tracer,
)
websocket_service = WebSocketService(rag_service, logger)
metrics_query = MetricsQueryService(config, rag_service.graph_runner.metrics_facts)
eval_store = create_eval_store(config)
# The runner shares the graph's backend client on purpose: an eval run must
# exercise the retrieval path the application actually uses, not a second one.
eval_runner = create_eval_runner(config, eval_store, backend_client, logger)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.log("main:startup", "RAG service starting up")
    conversation_store.ensure_indexes()
    rag_service.graph_runner.metrics_facts.ensure_indexes()
    eval_store.ensure_indexes()
    await rpc_client.connect()

    _consumer = MessageQueueFactory.create_consumer(config)

    async def _handle(body: dict, reply_to: str, correlation_id: str) -> Optional[dict]:
        from app.services.conversation_events import CollectingConversationEmitter
        body = dict(body)  # shallow copy
        body.setdefault("reply_to", reply_to)
        body.setdefault("correlation_id", correlation_id)

        # Action dispatch, following the shape the files service already
        # uses. Anything unrecognised - an absent action included - falls
        # through to the conversation graph, which is what every existing
        # caller relies on today.
        action = str(body.get("action") or "")
        if action == METRICS_ACTION:
            payload = extract_request_payload(body, correlation_id)
            return build_reply_envelope(body, metrics_query.handle(payload), correlation_id)
        if action in EVAL_ACTIONS:
            payload = extract_request_payload(body, correlation_id)
            result = await eval_runner.handle(action, payload)
            return build_reply_envelope(body, result, correlation_id)

        request = rag_service.build_request(extract_request_payload(body, correlation_id))
        emitter = CollectingConversationEmitter(request)
        result = await rag_service.graph_runner.run(request, emitter)
        return build_reply_envelope(body, result, correlation_id)

    try:
        await _consumer.start(_handle)
        yield
    finally:
        await _consumer.stop()
        await rpc_client.close()
        logger.log("main:shutdown", "RAG service shutdown complete", {})


# ---------------------------------------------------------------------------
# FastAPI + Socket.IO construction
# ---------------------------------------------------------------------------

fastapi_app = FastAPI(title="RAG Service", lifespan=lifespan)
setup_cors(fastapi_app)
register_exception_handlers(fastapi_app)
if _HAS_METRICS:
    setup_metrics(fastapi_app, "rag")
fastapi_app.include_router(api_router)
fastapi_app.dependency_overrides[get_rag_service] = lambda: rag_service

sio = socketio.AsyncServer(cors_allowed_origins=config.frontend_url, async_mode="asgi")
socketio_app = socketio.ASGIApp(sio, fastapi_app)


# ---------------------------------------------------------------------------
# Socket.IO event handlers
# ---------------------------------------------------------------------------

@sio.event
async def connect(sid, environ, auth=None):
    try:
        ticket = (auth or {}).get("ticket") if isinstance(auth, dict) else None
        identity = verify_auth_ticket(
            ticket or "",
            secret=config.internal_auth_secret,
            audience="rag",
            purpose="socket",
        )
    except AuthError:
        return False
    meta = websocket_service.register_connection(sid, identity)
    logger.log("websocket:connect", "Client connected", {"sid": sid, "connection_id": meta["connection_id"]})


@sio.event
async def disconnect(sid):
    websocket_service.unregister_connection(sid)
    logger.log("websocket:disconnect", "Client disconnected", {"sid": sid})


@sio.event
async def question(sid, data):
    try:
        await websocket_service.handle_question(sid, data or {}, sio)
    except Exception as exc:
        logger.error("websocket:question", "Question handler failed", exc)
        try:
            error_event = websocket_service.build_error_event(
                sid, data or {}, code="websocket_request_error",
                failed_node="question", retryable=True,
                message="The request could not be completed. Please try again.",
            )
        except Exception:
            error_event = {
                "type": "error",
                "data": {
                    "code": "socket_authentication_expired",
                    "retryable": True,
                    "message": "The secure connection expired. Please reconnect.",
                },
            }
        await sio.emit("error", error_event, room=sid)


@sio.event
async def answer_feedback(sid, data):
    await websocket_service.handle_feedback(sid, "answer_feedback", data or {}, sio)


@sio.event
async def flow_feedback(sid, data):
    await websocket_service.handle_feedback(sid, "flow_feedback", data or {}, sio)


# ---------------------------------------------------------------------------
# ASGI application export
# ---------------------------------------------------------------------------

app = socketio_app

if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run(socketio_app, host=config.service_host, port=config.service_port)
