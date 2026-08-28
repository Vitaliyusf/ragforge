"""Tests for the long-term memory domain service and Kafka handlers."""


from __future__ import annotations


import copy


from types import SimpleNamespace


from unittest.mock import Mock




from app.services.memory_service import LongTermMemoryService




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
