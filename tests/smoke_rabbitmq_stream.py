"""Smoke-test the RAG-to-LLM RabbitMQ stream path from the RAG container."""
import asyncio
import json
import time
from uuid import uuid4

from app.core.config import RAGConfig
from app.messaging.rpc_client import RabbitMQRPCClient
from app.services.conversation_messages import build_message_envelope, extract_stream_event


async def main() -> None:
    config = RAGConfig()
    client = RabbitMQRPCClient(config)
    request_id = f"stream-smoke-{uuid4()}"
    events = []

    async def on_event(message):
        events.append(extract_stream_event(message))

    envelope = build_message_envelope(
        message_type="command",
        action="answer_generation",
        source_service="rag",
        target_service="llm_agent",
        request_id=request_id,
        trace_id=request_id,
        payload={
            "request_type": "answer_generation",
            "input": {
                "question": "Reply with exactly three words.",
                "retrieved_context": [],
                "conversation_history": None,
                "instructions": "Use exactly three words.",
            },
            "metadata": {"request_id": request_id},
            "debug": {"include_visible_reasoning_steps": False},
        },
    )

    started = time.perf_counter()
    await client.connect()
    try:
        reply = await client.request_stream(
            config.llm_agent_routing_key,
            envelope,
            config.generation_request_timeout,
            on_event,
        )
    finally:
        await client.close()

    token_events = [event for event in events if event.get("event") == "delta"]
    completed = next((event for event in events if event.get("event") == "completed"), {})
    print(
        json.dumps(
            {
                "success": reply.get("success"),
                "event_types": [event.get("event") for event in events],
                "token_count": len(token_events),
                "reported_token_count": completed.get("token_count"),
                "text": "".join(event.get("text_delta", "") for event in token_events),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
