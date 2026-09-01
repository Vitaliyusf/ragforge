"""Completed-turn metadata contracts at the Gateway/RabbitMQ boundary."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.schemas.message import MessageRequest
from app.services.chat_history_service import ChatHistoryService


def test_message_request_sanitizes_durable_metadata() -> None:
    request = MessageRequest(
        message="Answer",
        sender="Assistant",
        metadata={
            "turnId": "turn-1",
            "sources": [{"source_name": "guide.pdf", "text": "private", "text_preview": "excerpt"}],
            "debugPayloads": {"visible_reasoning_summary": "summary", "generation_context": "private"},
            "providerPayload": {"secret": "never"},
        },
    )

    assert request.metadata["turnId"] == "turn-1"
    assert request.metadata["sources"] == [{"source_name": "guide.pdf", "text_preview": "excerpt"}]
    assert request.metadata["debugPayloads"] == {"visible_reasoning_summary": "summary"}
    assert "providerPayload" not in request.metadata


def test_add_message_forwards_metadata_to_memory_rpc() -> None:
    rpc_client = MagicMock()
    rpc_client.send_request = AsyncMock(return_value={"status": "success"})
    config = MagicMock(short_timeout=10.0, request_topics={"memory": "memory"})
    service = ChatHistoryService(rpc_client, MagicMock(), config)
    request = MessageRequest(
        message="Answer",
        sender="Assistant",
        metadata={"turnId": "turn-1", "answerReview": {"verdict": "pass"}},
    )

    asyncio.run(service.add_message("chat-1", request))

    payload = rpc_client.send_request.await_args.args[1]
    assert payload["metadata"] == {
        "turnId": "turn-1",
        "answerReview": {"verdict": "pass"},
    }
