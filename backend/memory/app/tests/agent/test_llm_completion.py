"""Typed llm_agent requests used by chat-exit orchestration."""
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.chat_exit_service import ChatExitService


def test_repeated_typed_llm_calls_reuse_the_injected_process_transport(monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_exit_service.verify_internal_ticket_from_envelope",
        lambda *_args, **_kwargs: None,
    )
    transport = Mock()
    transport.request_from_thread.return_value = {
        "success": True,
        "payload": {"parsed_output": {"title": "Beta launch"}},
    }
    service = ChatExitService(Mock(), Mock(), Mock(), Mock(), transport)

    result = service._request_typed_llm(
        "chat_title",
        {"conversation_history": [{"role": "user", "content": "We launched."}]},
        15.0,
    )

    second = service._request_typed_llm(
        "chat_title",
        {"conversation_history": []},
        15.0,
    )

    assert result["title"] == "Beta launch"
    assert second["title"] == "Beta launch"
    assert transport.request_from_thread.call_count == 2


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


def test_memory_curation_applies_validated_actions_through_canonical_write_service(monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_exit_service.current_identity",
        lambda: SimpleNamespace(tenant_id="tenant-1", user_id="user-1", role="user"),
    )
    memory_service = Mock()
    memory_service.get_relevant_memories.return_value = {
        "memories": [{"id": "allowed", "content": {"text": "Old"}, "category": "chat_insight"}]
    }
    memory_service.write_memory.side_effect = [
        {"status": "accepted", "memory_id": "new-1"},
        {"status": "accepted", "memory_id": "replacement-1"},
    ]
    service = ChatExitService(Mock(), Mock(), memory_service, Mock())
    service._request_typed_llm = Mock(
        return_value={
            "actions": [
                {"action": "create", "content": "New preference", "category": "user_preference"},
                {"action": "update", "memory_id": "allowed", "content": "Updated"},
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
        {
            "tenant_id": "tenant-1",
            "owner_id": "user-1",
            "role": "user",
            "request_id": "req-1",
            "trace_id": "trace-1",
        },
    )

    service._request_typed_llm.assert_called_once()
    assert service._request_typed_llm.call_args.args[0] == "memory_curation"
    assert memory_service.write_memory.call_count == 2
    assert memory_service.write_memory.call_args_list[0].args[0]["content"]["text"] == "New preference"
    assert memory_service.write_memory.call_args_list[1].args[0]["supersedes"] == "allowed"
    memory_service.delete_memory.assert_not_called()


def test_memory_curation_rejects_the_whole_plan_when_an_id_is_outside_the_bound(monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_exit_service.current_identity",
        lambda: SimpleNamespace(tenant_id="tenant-1", user_id="user-1", role="user"),
    )
    memory_service = Mock()
    memory_service.get_relevant_memories.return_value = {
        "memories": [{"id": "allowed", "content": {"text": "Old"}}]
    }
    service = ChatExitService(Mock(), Mock(), memory_service, Mock())
    service._request_typed_llm = Mock(
        return_value={
            "actions": [{"action": "update", "memory_id": "cross-tenant", "content": "Changed"}],
            "summary": "unsafe",
        }
    )

    result = service._curate_memories(
        [{"sender": "User", "message": "Remember this"}, {"sender": "Assistant", "message": "Okay"}],
        "chat-1",
        {
            "tenant_id": "tenant-1",
            "owner_id": "user-1",
            "role": "user",
            "request_id": "req-1",
            "trace_id": "trace-1",
        },
    )

    assert result.status == "fallback"
    memory_service.write_memory.assert_not_called()
    memory_service.delete_memory.assert_not_called()
