"""Typed llm_agent requests used by chat-exit orchestration."""
from unittest.mock import AsyncMock, Mock

from app.services.chat_exit_service import ChatExitService


def test_request_typed_llm_runs_the_async_rpc(monkeypatch):
    service = ChatExitService(Mock(), Mock(), Mock(), Mock())
    transport = AsyncMock(return_value={"title": "Beta launch"})
    monkeypatch.setattr(service, "_request_typed_llm_async", transport)

    result = service._request_typed_llm(
        "chat_title",
        {"conversation_history": [{"role": "user", "content": "We launched."}]},
        15.0,
    )

    assert result == {"title": "Beta launch"}
    transport.assert_awaited_once()


def test_conversation_history_normalizes_sender_roles():
    history = ChatExitService._conversation_history(
        [
            {"sender": "User", "message": "Question"},
            {"sender": "Assistant", "message": "Answer"},
            {"sender": "unexpected", "message": "Fallback"},
        ]
    )

    assert history == [
        {"role": "user", "content": "Question"},
        {"role": "assistant", "content": "Answer"},
        {"role": "user", "content": "Fallback"},
    ]


def test_memory_curation_applies_only_actions_for_supplied_memory_ids():
    memory_service = Mock()
    memory_service.get_all_memories.return_value = [
        {"id": "allowed", "content": "Old", "category": "chat_insight"}
    ]
    service = ChatExitService(Mock(), Mock(), memory_service, Mock())
    service._request_typed_llm = Mock(
        return_value={
            "actions": [
                {"action": "add", "content": "New preference", "category": "user_preference"},
                {"action": "update", "memory_id": "allowed", "content": "Updated"},
                {"action": "delete", "memory_id": "not-supplied"},
            ],
            "summary": "Added and updated memory",
        }
    )

    service._curate_memories(
        [
            {"sender": "User", "message": "Remember this"},
            {"sender": "Assistant", "message": "Okay"},
        ],
        "chat-1",
    )

    service._request_typed_llm.assert_called_once()
    assert service._request_typed_llm.call_args.args[0] == "memory_curation"
    memory_service.create_memory.assert_called_once_with(
        "New preference",
        "user_preference",
        {"source": "llm_agent", "chat_id": "chat-1"},
    )
    memory_service.update_memory.assert_called_once_with("allowed", content="Updated")
    memory_service.delete_memory.assert_not_called()
