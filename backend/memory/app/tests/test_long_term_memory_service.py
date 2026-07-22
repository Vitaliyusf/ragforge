"""Tests for the long-term memory domain service and Kafka handlers."""
from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.memory_handler_service import MemoryHandlerService
from app.services.memory_service import LongTermMemoryService
from shared.context import bound_context


def _get_nested(document, dotted_key):
    value = document
    for part in dotted_key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _set_nested(document, dotted_key, value):
    parts = dotted_key.split(".")
    cursor = document
    for part in parts[:-1]:
        if part not in cursor or not isinstance(cursor[part], dict):
            cursor[part] = {}
        cursor = cursor[part]
    cursor[parts[-1]] = value


class FakeCursor(list):
    """Very small cursor shim with sorting support."""

    def sort(self, key, direction):
        reverse = direction == -1
        return FakeCursor(sorted(self, key=lambda item: _get_nested(item, key) or "", reverse=reverse))


class FakeCollection:
    """In-memory collection implementation for tests."""

    def __init__(self):
        self.docs = []
        self.indexes = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    def _matches(self, document, query):
        for key, expected in (query or {}).items():
            actual = _get_nested(document, key)
            if isinstance(expected, dict):
                if "$in" in expected and actual not in expected["$in"]:
                    return False
                continue
            if actual != expected:
                return False
        return True

    def _project(self, document, projection):
        cloned = copy.deepcopy(document)
        if not isinstance(projection, dict):
            return cloned
        if projection.get("_id") == 0:
            cloned.pop("_id", None)
        return cloned

    def insert_one(self, document):
        self.docs.append(copy.deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("id"))

    def find(self, query=None, projection=None):
        return FakeCursor([self._project(doc, projection) for doc in self.docs if self._matches(doc, query or {})])

    def find_one(self, query=None, projection=None):
        for doc in self.docs:
            if self._matches(doc, query or {}):
                return self._project(doc, projection)
        return None

    def update_one(self, query, update):
        modified = 0
        for doc in self.docs:
            if self._matches(doc, query):
                for key, value in update.get("$set", {}).items():
                    _set_nested(doc, key, copy.deepcopy(value))
                modified = 1
                break
        return SimpleNamespace(modified_count=modified)

    def delete_one(self, query):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                del self.docs[index]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    def delete_many(self, query):
        original = len(self.docs)
        self.docs = [doc for doc in self.docs if not self._matches(doc, query)]
        return SimpleNamespace(deleted_count=original - len(self.docs))


class FakeDatabase(dict):
    """Dictionary-backed database shim."""

    def __getitem__(self, name):
        if name not in self:
            self[name] = FakeCollection()
        return super().__getitem__(name)


class FakeQdrantIndex:
    """Fake Qdrant index used for retrieval and failure tests."""

    def __init__(self, enabled=False, search_results=None, fail_index=False):
        self.enabled = enabled
        self.search_results = list(search_results or [])
        self.fail_index = fail_index
        self.indexed_ids = []
        self.deleted_ids = []

    def is_enabled(self):
        return self.enabled

    def index_memory(self, memory_doc):
        if self.fail_index:
            raise RuntimeError("qdrant indexing failed")
        self.indexed_ids.append(memory_doc["id"])
        return True

    def search(self, query_text, owner_id, owner_type, limit):
        del query_text, owner_id, owner_type
        return self.search_results[:limit]

    def delete_memory(self, memory_id):
        self.deleted_ids.append(memory_id)


class FakeProducer:
    """Capture replies and completion events."""

    def __init__(self):
        self.replies = []
        self.completed_events = []

    def send_reply(self, topic, message):
        self.replies.append(
            {
                "topic": topic,
                "message": copy.deepcopy(message),
            }
        )
        return topic

    def publish_write_completed(self, event):
        self.completed_events.append(copy.deepcopy(event))


def kafka_envelope(
    action,
    payload,
    *,
    message_type="command",
    source_service="rag",
    target_service="memory",
    request_id="req-1",
    trace_id="trace-1",
    correlation_id="corr-1",
    reply_to="rag.replies",
    timestamp="2026-03-17T12:00:00+00:00",
):
    """Build a canonical shared-envelope Kafka request."""
    envelope = {
        "message_id": f"msg-{correlation_id}",
        "message_type": message_type,
        "action": action,
        "source_service": source_service,
        "target_service": target_service,
        "request_id": request_id,
        "trace_id": trace_id,
        "correlation_id": correlation_id,
        "timestamp": timestamp,
        "payload": copy.deepcopy(payload),
    }
    if reply_to is not None:
        envelope["reply_to"] = reply_to
    return envelope


def build_memory_service(index_client=None):
    """Create a service with an isolated in-memory database."""
    database = FakeDatabase()
    logger = Mock()
    service = LongTermMemoryService(
        logger=logger,
        db_provider=lambda: database,
        index_client=index_client or FakeQdrantIndex(enabled=False),
        now_fn=lambda: "2026-03-17T12:00:00+00:00",
    )
    return service, database, logger


def episodic_candidate(text="The user launched the beta milestone."):
    """Build a valid episodic memory candidate."""
    return {
        "content": {"text": text, "summary": "Beta launch milestone"},
        "event_at": "2026-03-01T00:00:00+00:00",
        "importance": 0.9,
        "confidence": 0.8,
        "tags": ["launch", "milestone"],
        "provenance": {"explicit_user_signal": True, "chat_id": "chat-1"},
    }


def preference_candidate(text="The user explicitly prefers concise answers with citations."):
    """Build a valid semantic preference candidate."""
    return {
        "content": {"text": text, "summary": "Prefers concise answers and citations"},
        "preference_key": "response_style",
        "value": "concise",
        "importance": 0.85,
        "confidence": 0.9,
        "provenance": {"explicit_user_signal": True, "stable_feedback_count": 2},
        "tags": ["preference", "concise", "citations"],
    }


def test_write_memory_accepts_episodic_memory():
    service, database, _ = build_memory_service()

    result = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-1", "trace_id": "trace-1"},
    )

    assert result["status"] == "accepted"
    assert result["memory_class"] == "episodic"
    assert len(database["episodic_memories"].docs) == 1
    assert database["memory_write_log"].docs[0]["status"] == "accepted"


def test_write_memory_accepts_and_upserts_semantic_preference():
    service, database, _ = build_memory_service()

    first = service.write_memory(
        preference_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-2"},
    )
    second = service.write_memory(
        preference_candidate("The user again asked for concise answers with citations."),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-3"},
    )

    assert first["status"] == "accepted"
    assert second["status"] == "merged"
    assert len(database["semantic_preferences"].docs) == 1
    stored = database["semantic_preferences"].docs[0]
    assert stored["preference_key"] == "response_style"
    assert stored["evidence_count"] >= 2


def test_write_memory_rejects_transient_candidates():
    service, database, _ = build_memory_service()

    result = service.write_memory(
        {
            "content": {"text": "The user is currently working on this for now and will revisit next turn."},
            "importance": 0.8,
            "confidence": 0.9,
        },
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-4"},
    )

    assert result["status"] == "rejected"
    assert "temporary task state" in result["reason"]
    assert len(database["episodic_memories"].docs) == 0
    assert database["memory_write_log"].docs[0]["status"] == "rejected"


def test_write_memory_rejects_retrieval_dump_candidates():
    service, database, _ = build_memory_service()

    result = service.write_memory(
        {
            "content": {"text": "page_content: chunk 14 document: retrieval result embedding score=0.93"},
            "importance": 0.8,
            "confidence": 0.9,
        },
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-5"},
    )

    assert result["status"] == "rejected"
    assert "retrieval dumps" in result["reason"]
    assert len(database["memory_write_log"].docs) == 1


def test_write_memory_rejects_hidden_reasoning_candidates():
    service, _, _ = build_memory_service()

    result = service.write_memory(
        {
            "content": {"text": "Internal scratchpad chain of thought about the user's intent."},
            "importance": 0.8,
            "confidence": 0.8,
        },
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-6"},
    )

    assert result["status"] == "rejected"
    assert "hidden reasoning" in result["reason"]


def test_get_relevant_memories_returns_owner_scoped_results_and_excludes_archived():
    service, database, _ = build_memory_service()
    episodic = episodic_candidate()
    semantic = preference_candidate()

    accepted = service.write_memory(episodic, {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-7"})
    service.write_memory(semantic, {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-8"})
    service.write_memory(episodic_candidate("Another owner's milestone"), {"owner_id": "owner-2", "owner_type": "user", "request_id": "req-9"})

    archived_id = accepted["memory_id"]
    database["episodic_memories"].update_one({"id": archived_id}, {"$set": {"archived_at": "2026-03-18T00:00:00+00:00"}})

    result = service.get_relevant_memories(
        {
            "owner_id": "owner-1",
            "owner_type": "user",
            "text": "Please stay concise and use citations.",
            "limit": 5,
        }
    )

    assert all(item["owner_id"] == "owner-1" for item in result["memories"])
    assert all(item["archived_at"] is None for item in result["memories"])
    assert len(result["memories"]) == 1
    assert result["memories"][0]["memory_class"] == "semantic_preference"


def test_get_relevant_memories_balances_episodic_and_semantic_preference():
    index = FakeQdrantIndex(
        enabled=True,
        search_results=[
            {"memory_id": "episodic-1", "score": 0.95},
            {"memory_id": "pref-1", "score": 0.94},
            {"memory_id": "pref-2", "score": 0.93},
            {"memory_id": "pref-3", "score": 0.92},
        ],
    )
    service, database, _ = build_memory_service(index_client=index)

    database["episodic_memories"].insert_one(
        {
            "id": "episodic-1",
            "owner_id": "owner-1",
            "owner_type": "user",
            "memory_class": "episodic",
            "content": {"text": "The user launched the beta.", "summary": "Beta launch"},
            "source": "manual",
            "confidence": 0.9,
            "importance": 0.8,
            "tags": ["launch"],
            "created_at": "2026-03-01T00:00:00+00:00",
            "updated_at": "2026-03-17T12:00:00+00:00",
            "last_accessed_at": None,
            "archived_at": None,
            "provenance": {"explicit_user_signal": True},
            "retrieval": {"keywords": ["launch", "beta"], "embedding_status": "indexed", "qdrant_point_id": "episodic-1"},
            "event_at": "2026-03-01T00:00:00+00:00",
            "expires_at": None,
            "stability": 0.9,
        }
    )
    for idx in range(1, 4):
        database["semantic_preferences"].insert_one(
            {
                "id": f"pref-{idx}",
                "owner_id": "owner-1",
                "owner_type": "user",
                "memory_class": "semantic_preference",
                "content": {"text": f"Preference {idx}", "summary": f"Preference {idx}"},
                "source": "manual",
                "confidence": 0.9,
                "importance": 0.7,
                "tags": ["preference"],
                "created_at": "2026-03-01T00:00:00+00:00",
                "updated_at": "2026-03-17T12:00:00+00:00",
                "last_accessed_at": None,
                "archived_at": None,
                "provenance": {"explicit_user_signal": True},
                "retrieval": {"keywords": ["preference", str(idx)], "embedding_status": "indexed", "qdrant_point_id": f"pref-{idx}"},
                "preference_key": f"pref-key-{idx}",
                "value": "value",
                "value_type": "string",
                "strength": 0.9,
                "evidence_count": 3,
            }
        )

    result = service.get_relevant_memories(
        {"owner_id": "owner-1", "owner_type": "user", "text": "launch preferences", "limit": 4}
    )

    classes = [item["memory_class"] for item in result["memories"]]
    assert "episodic" in classes
    assert classes.count("semantic_preference") <= 2


def test_write_memory_preserves_accepted_status_when_qdrant_fails():
    index = FakeQdrantIndex(enabled=True, fail_index=True)
    service, database, _ = build_memory_service(index_client=index)

    result = service.write_memory(
        episodic_candidate(),
        {"owner_id": "owner-1", "owner_type": "user", "request_id": "req-10"},
    )

    assert result["status"] == "accepted"
    assert result["qdrant_indexed"] is False
    assert database["episodic_memories"].docs[0]["retrieval"]["embedding_status"] == "failed"
    assert database["memory_write_log"].docs[0]["qdrant_error"] == "qdrant indexing failed"


def test_retrieval_honors_owner_id_and_owner_type():
    service, _, _ = build_memory_service()
    service.write_memory(episodic_candidate(), {"owner_id": "session-1", "owner_type": "session", "request_id": "req-11"})
    service.write_memory(episodic_candidate("Conversation memory"), {"owner_id": "conv-1", "owner_type": "conversation", "request_id": "req-12"})

    result = service.get_relevant_memories(
        {"owner_id": "conv-1", "owner_type": "conversation", "text": "Conversation memory", "limit": 5}
    )

    assert len(result["memories"]) == 1
    assert result["memories"][0]["owner_type"] == "conversation"
    assert result["memories"][0]["owner_id"] == "conv-1"


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
            handler.process_request(
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
            ),
            handler.process_request(
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
            ),
            handler.process_write_requested(
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
            ),
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


def test_memory_handler_accepts_legacy_request_without_trusting_owner_fields():
    service, database, logger = build_memory_service()
    handler = MemoryHandlerService(
        chat_service=Mock(),
        message_service=Mock(),
        memory_service=service,
        chat_exit_service=Mock(),
        logger=logger,
    )

    with bound_context(tenant_id="tenant-a", user_id="trusted-owner", role="user"):
        reply = handler.process_request(
            {
                "correlation_id": "corr-legacy",
                "trace_id": "trace-legacy",
                "action": "write_memory",
                "owner_id": "untrusted-owner",
                "owner_type": "conversation",
                "candidate": episodic_candidate(),
            }
        )

    stored = database["episodic_memories"].docs[0]
    assert stored["owner_id"] == "trusted-owner"
    assert stored["owner_type"] == "user"
    assert stored["tenant_id"] == "tenant-a"
    assert reply["message_type"] == "reply"
    assert reply["source_service"] == "memory"
    assert reply["target_service"] == "unknown"
    assert reply["correlation_id"] == "corr-legacy"
    assert reply["success"] is True
    assert reply["payload"]["status"] == "accepted"


def test_user_insight_surfaces_remain_deprecated_and_non_persistent():
    service, _, _ = build_memory_service()

    created = service.update_user_insight("The user prefers concise answers.")

    assert service.get_user_insight() is None
    assert created["category"] == "user_insight"
    assert created["metadata"]["deprecated"] is True
    assert service.get_all_memories() == []
