"""Tests for the long-term memory domain service and Kafka handlers."""


from __future__ import annotations


import copy
import hashlib
import math
import re


from types import SimpleNamespace


from typing import cast


from unittest.mock import Mock




from app.services.memory_embedding_client import MemoryEmbeddingClient, MemoryEmbeddingError
from app.services.memory_reconciliation import MemoryReconciliationService
from app.services.memory_service import LongTermMemoryService
from app.services.memory_vector_index import MemoryVectorIndex, MemoryVectorIndexError
from app.services.tenant_scope import current_identity




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
            # `scope_filter` wraps the tenant/user boundary and the caller's
            # own filter in `$and`, so the fake has to honour it or every
            # scoped query would silently match nothing and isolation tests
            # would pass for the wrong reason.
            if key == "$and":
                if not all(self._matches(document, clause) for clause in expected):
                    return False
                continue
            if key == "$or":
                if not any(self._matches(document, clause) for clause in expected):
                    return False
                continue
            actual = _get_nested(document, key)
            if isinstance(expected, dict):
                if "$in" in expected and actual not in expected["$in"]:
                    return False
                if "$ne" in expected and actual == expected["$ne"]:
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


class FakeVectorIndex:
    """Fake memory vector index used for retrieval and failure tests."""

    collection_name = "memory_items_test"

    def __init__(
        self,
        enabled=False,
        search_results=None,
        fail_index=False,
        fail_delete=False,
        points=None,
        fail_scroll=False,
    ):
        self.enabled = enabled
        self.search_results = list(search_results or [])
        self.fail_index = fail_index
        self.fail_delete = fail_delete
        self.fail_scroll = fail_scroll
        self.points = list(points or [])
        self.indexed_ids = []
        self.deleted_ids = []
        self.deleted_point_ids = []
        self.searched_vectors = []

    def is_enabled(self):
        return self.enabled

    def upsert_memory(self, memory_doc, vector):
        if self.fail_index:
            raise MemoryVectorIndexError("vector upsert failed")
        self.indexed_ids.append(memory_doc["id"])
        return f"point-{memory_doc['id']}"

    def search(self, vector, owner_id, owner_type, limit, statuses=None):
        del owner_id, owner_type, statuses
        self.searched_vectors.append(list(vector))
        return self.search_results[:limit]

    def delete_memory(self, memory_id):
        if self.fail_delete:
            raise MemoryVectorIndexError("vector delete failed")
        self.deleted_ids.append(memory_id)
        self.points = [
            point for point in self.points
            if (point.get("payload") or {}).get("memory_id") != memory_id
        ]

    def point_id(self, tenant_id, user_id, memory_id):
        return f"point-{tenant_id}:{user_id}:{memory_id}"

    def scroll_points(self, limit, offset=None):
        if self.fail_scroll:
            raise MemoryVectorIndexError("vector scroll failed")
        del offset
        return list(self.points[:limit]), None

    def delete_point(self, point_id):
        if self.fail_delete:
            raise MemoryVectorIndexError("vector point delete failed")
        self.deleted_point_ids.append(point_id)
        self.points = [point for point in self.points if point.get("point_id") != point_id]


class InMemoryVectorIndex:
    """Vector index that really stores vectors and ranks by cosine similarity.

    `FakeVectorIndex` is enough to test wiring and failure handling, but a
    retrieval-quality measurement has to exercise the actual ranking path, so
    this one keeps points, applies the same tenant/user/status filters the
    Qdrant client applies, and scores with cosine similarity.
    """

    collection_name = "memory_items_measurement"

    def __init__(self):
        self.points = {}

    def is_enabled(self):
        return True

    @staticmethod
    def _cosine(left, right):
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def upsert_memory(self, memory_doc, vector):
        identity = current_identity()
        point_id = f"{identity.tenant_id}:{identity.user_id}:{memory_doc['id']}"
        self.points[point_id] = {
            "vector": list(vector),
            "payload": {
                "memory_id": memory_doc["id"],
                "owner_id": memory_doc["owner_id"],
                "owner_type": memory_doc["owner_type"],
                "status": memory_doc.get("status", "active"),
                "revision": memory_doc.get("revision", 1),
                "valid_to": memory_doc.get("valid_to"),
                "archived": bool(memory_doc.get("archived_at")),
                "tenant_id": identity.tenant_id,
                "owner_user_id": identity.user_id,
            },
        }
        return point_id

    def search(self, vector, owner_id, owner_type, limit, statuses=None):
        identity = current_identity()
        allowed = set(statuses or ["active"])
        hits = []
        for point in self.points.values():
            payload = point["payload"]
            if payload["owner_id"] != owner_id or payload["owner_type"] != owner_type:
                continue
            if payload["status"] not in allowed or payload["archived"]:
                continue
            if identity is not None and (
                payload["tenant_id"] != identity.tenant_id
                or payload["owner_user_id"] != identity.user_id
            ):
                continue
            hits.append(
                {
                    "memory_id": payload["memory_id"],
                    "score": self._cosine(vector, point["vector"]),
                    "payload": payload,
                }
            )
        hits.sort(key=lambda hit: (hit["score"], hit["memory_id"]), reverse=True)
        return hits[:limit]

    def delete_memory(self, memory_id):
        for point_id in [
            key for key, point in self.points.items() if point["payload"]["memory_id"] == memory_id
        ]:
            del self.points[point_id]

    def point_id(self, tenant_id, user_id, memory_id):
        return f"{tenant_id}:{user_id}:{memory_id}"

    def scroll_points(self, limit, offset=None):
        del offset
        identity = current_identity()
        mine = [
            {"point_id": point_id, "payload": point["payload"]}
            for point_id, point in sorted(self.points.items())
            if identity is None
            or (
                point["payload"]["tenant_id"] == identity.tenant_id
                and point["payload"]["owner_user_id"] == identity.user_id
            )
        ]
        return mine[:limit], None

    def delete_point(self, point_id):
        self.points.pop(point_id, None)


class BagOfWordsEmbeddingClient:
    """Deterministic bag-of-words embedding used for measurement only.

    This is a real (if weak) semantic model: texts that share vocabulary get
    similar vectors, which is what makes a retrieval-quality number meaningful
    rather than a coin flip. It is emphatically NOT the production model, and
    every number measured with it must be reported as such.

    Tokenization is Unicode-aware so a Hebrew or mixed Hebrew/English corpus
    produces real vectors instead of an all-zero one; an ASCII-only stub would
    have reported the multilingual path as broken no matter how the service
    behaved.
    """

    model = "bag-of-words-measurement-stub"

    def __init__(self, dimensions=256):
        self._dimensions = dimensions

    @property
    def dimensions(self):
        return self._dimensions

    def provenance(self):
        return {"model": self.model, "dimensions": self._dimensions, "service": "in-process-stub"}

    def _vector(self, text):
        vector = [0.0] * self._dimensions
        for token in re.findall(r"[\w+-]+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            vector[int(digest[:8], 16) % self._dimensions] += 1.0
        return vector

    def embed_memory(self, text):
        return self._vector(text)

    def embed_query(self, text):
        return self._vector(text)


class FakeEmbeddingClient:
    """Deterministic stand-in for the canonical embedding service RPC."""

    def __init__(self, dimensions=8, fail=False, model="fake-embedding-model"):
        self._dimensions = dimensions
        self.fail = fail
        self._model = model
        self.embedded_passages = []
        self.embedded_queries = []

    @property
    def model(self):
        return self._model

    @property
    def dimensions(self):
        return self._dimensions

    def provenance(self):
        return {"model": self._model, "dimensions": self._dimensions, "service": "embedding"}

    def _vector(self, text):
        if self.fail:
            raise MemoryEmbeddingError("embedding service unavailable")
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[index % len(digest)] / 255.0 for index in range(self._dimensions)]

    def embed_memory(self, text):
        vector = self._vector(text)
        self.embedded_passages.append(text)
        return vector

    def embed_query(self, text):
        vector = self._vector(text)
        self.embedded_queries.append(text)
        return vector


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


def build_memory_service(index_client=None, embedding_client=None):
    """Create a service with an isolated in-memory database."""
    database = FakeDatabase()
    logger = Mock()
    # The fakes stand in for the real collaborators structurally, not by
    # inheritance, so the casts say "substitute" rather than loosening the
    # service's own annotations.
    service = LongTermMemoryService(
        logger=logger,
        db_provider=lambda: database,
        index_client=cast(MemoryVectorIndex, index_client or FakeVectorIndex(enabled=False)),
        now_fn=lambda: "2026-03-17T12:00:00+00:00",
        embedding_client=cast(MemoryEmbeddingClient, embedding_client or FakeEmbeddingClient()),
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


def build_reconciliation_service(service, logger=None):
    """Wrap a memory service in its reconciler, sharing the same fakes."""
    return MemoryReconciliationService(service, logger or Mock())
