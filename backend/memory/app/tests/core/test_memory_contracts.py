"""The shared request/reply envelope the memory handler speaks."""

from unittest.mock import Mock

from app.services.memory_handler_service import MemoryHandlerService
from shared.context import bound_context

from app.tests._memory_harness import (
    FakeEmbeddingClient,
    FakeVectorIndex,
    build_memory_service,
    episodic_candidate,
    kafka_envelope,
    preference_candidate,
)


def _reply(reply):
    """Return a handler reply, failing loudly when the handler sent none."""
    assert reply is not None
    return reply


def test_memory_handler_supports_shared_envelope_request_reply_and_completed_event():
    service, _, logger = build_memory_service()
    chat_service = Mock()
    message_service = Mock()
    chat_exit_service = Mock()
    handler = MemoryHandlerService(
        chat_service=chat_service,
        message_service=message_service,
        memory_service=service,
        chat_exit_service=chat_exit_service,
        logger=logger,
    )

    with bound_context(tenant_id="tenant-a", user_id="owner-1", role="user"):
        replies = [
            _reply(handler.process_request(
                kafka_envelope(
                    "write_memory",
                    {
                        "owner_id": "untrusted-owner",
                        "owner_type": "conversation",
                        "candidate": episodic_candidate(),
                    },
                    message_type="command",
                    source_service="rag",
                    request_id="req-13",
                    trace_id="trace-13",
                    correlation_id="corr-13",
                    reply_to="rag.replies",
                )
            )),
            _reply(handler.process_request(
                kafka_envelope(
                    "get_relevant_memories",
                    {
                        "owner_id": "untrusted-owner",
                        "owner_type": "conversation",
                        "query_context": {"text": "beta launch", "limit": 3},
                    },
                    message_type="query",
                    source_service="rag",
                    request_id="req-14",
                    trace_id="trace-14",
                    correlation_id="corr-14",
                    reply_to="rag.replies",
                )
            )),
            _reply(handler.process_write_requested(
                kafka_envelope(
                    "write_memory",
                    {
                        "owner_id": "untrusted-owner",
                        "owner_type": "conversation",
                        "candidate": preference_candidate(),
                    },
                    message_type="command",
                    source_service="gateway",
                    request_id="async-1",
                    trace_id="trace-3",
                    correlation_id="corr-3",
                    reply_to="gateway.replies",
                )
            )),
        ]

    assert replies[0]["message_type"] == "reply"
    assert replies[0]["source_service"] == "memory"
    assert replies[0]["target_service"] == "rag"
    assert replies[0]["correlation_id"] == "corr-13"
    assert replies[0]["success"] is True
    assert replies[0]["payload"]["status"] == "accepted"

    assert replies[1]["message_type"] == "reply"
    assert replies[1]["target_service"] == "rag"
    assert replies[1]["payload"]["status"] == "success"
    assert len(replies[1]["payload"]["memories"]) == 1

    assert replies[2]["message_type"] == "reply"
    assert replies[2]["target_service"] == "gateway"
    assert replies[2]["payload"]["status"] in {"accepted", "merged"}
    assert any(
        call.args and call.args[0] == "handler:write_completed"
        for call in logger.log.call_args_list
    )


def test_memory_handler_exposes_reconciliation_as_a_bounded_request():
    index = FakeVectorIndex(enabled=True)
    embedding = FakeEmbeddingClient(fail=True)
    service, database, logger = build_memory_service(index_client=index, embedding_client=embedding)
    handler = MemoryHandlerService(
        chat_service=Mock(),
        message_service=Mock(),
        memory_service=service,
        chat_exit_service=Mock(),
        logger=logger,
    )

    with bound_context(tenant_id="tenant-a", user_id="owner-1", role="user"):
        service.write_memory(
            episodic_candidate(),
            {"owner_type": "user", "request_id": "req-recon-1"},
        )
        drift = _reply(
            handler.process_request(
                kafka_envelope("memory_drift_report", {}, message_type="query", correlation_id="corr-30")
            )
        )
        embedding.fail = False
        repair = _reply(
            handler.process_request(
                kafka_envelope(
                    "reconcile_memory_index",
                    {"limit": 5},
                    message_type="command",
                    correlation_id="corr-31",
                )
            )
        )

    assert drift["success"] is True
    assert drift["payload"]["pending_count"] == 1
    assert repair["success"] is True
    assert repair["payload"]["repaired"] == 1
    assert repair["payload"]["failed"] == 0
    assert database["episodic_memories"].docs[0]["retrieval"]["embedding_status"] == "indexed"
