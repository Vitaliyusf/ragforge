"""Authorization tests for data crossing the browser socket boundary."""
from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.conversation_events import CollectingConversationEmitter
from app.services.conversation_types import ConversationRequest


def _request(role: str) -> ConversationRequest:
    return ConversationRequest(
        user_message="hello",
        tenant_id="tenant-a",
        user_id=f"{role}-a",
        role=role,
        admin_id="admin-a",
    )


@pytest.mark.asyncio
async def test_regular_user_never_receives_trace_events() -> None:
    emitter = CollectingConversationEmitter(_request("user"))
    result = await emitter.emit("trace", {"node": "retriever", "decision": "internal"})

    assert result == {}
    assert emitter.events == []


@pytest.mark.asyncio
async def test_regular_user_done_event_strips_debug_payloads_without_mutating_source() -> None:
    emitter = CollectingConversationEmitter(_request("user"))
    payload = {
        "final_answer": "safe answer",
        "trace_summary": [{"node": "generator"}],
        "safe_debug_payloads": {"system_prompt": "internal prompt"},
        "debug_payloads": {"raw_output": "internal output"},
    }
    original = deepcopy(payload)

    event = await emitter.emit("done", payload)

    assert event["data"] == {"final_answer": "safe answer"}
    assert payload == original


@pytest.mark.asyncio
async def test_admin_receives_operational_trace_and_debug_payloads() -> None:
    emitter = CollectingConversationEmitter(_request("admin"))
    trace = await emitter.emit("trace", {"node": "retriever"})
    done = await emitter.emit(
        "done",
        {"final_answer": "answer", "safe_debug_payloads": {"system_prompt": "prompt"}},
    )

    assert trace["data"]["node"] == "retriever"
    assert done["data"]["safe_debug_payloads"]["system_prompt"] == "prompt"
