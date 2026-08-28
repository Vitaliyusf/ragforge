"""Persistence layer for conversation state, checkpoints, reviews, and feedback."""
from __future__ import annotations

import asyncio
import copy
import os
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar

from app.core.config import RAGConfig
from shared.auth import identity_from_context


T = TypeVar("T")


def _identity():
    required = os.getenv("INTERNAL_AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"}
    return identity_from_context(required=required)


def _ownership() -> Dict[str, str]:
    identity = _identity()
    if identity is None:
        return {}
    return {
        "tenant_id": identity.tenant_id,
        "owner_user_id": identity.user_id,
        "owner_admin_id": identity.admin_id or identity.user_id,
    }


def _scope(query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    identity = _identity()
    source = dict(query or {})
    if identity is None:
        return source
    boundary = {"tenant_id": identity.tenant_id, "owner_user_id": identity.user_id}
    return boundary if not source else {"$and": [boundary, source]}


def _owned_document(document: Dict[str, Any]) -> Dict[str, Any]:
    return {**make_json_safe(document), **_ownership()}


def _memory_key(identifier: str) -> str:
    identity = _identity()
    return identifier if identity is None else f"{identity.tenant_id}:{identity.user_id}:{identifier}"

try:
    from pymongo import MongoClient
    from pymongo.collection import Collection
    _HAS_PYMONGO = True
except ImportError:  # pragma: no cover - exercised by fallback tests
    MongoClient = None
    Collection = Any
    _HAS_PYMONGO = False


def make_json_safe(value: Any) -> Any:
    """Recursively convert values into JSON-safe primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): make_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return make_json_safe(value.tolist())
    return str(value)


class BaseConversationStore:
    """Abstract persistence contract used by the conversation runtime."""

    def ensure_indexes(self) -> None:
        """Ensure backend indexes are ready."""
        return None

    def is_available(self) -> bool:
        """Return whether the configured store can serve persistence calls."""
        return True

    def load_context(self, conversation_id: str, recent_limit: int) -> Dict[str, Any]:
        raise NotImplementedError

    def save_thread(self, document: Dict[str, Any]) -> None:
        raise NotImplementedError

    def save_turn(self, document: Dict[str, Any]) -> None:
        raise NotImplementedError

    def save_summary(self, document: Dict[str, Any]) -> None:
        raise NotImplementedError

    def save_answer_review(self, document: Dict[str, Any]) -> None:
        raise NotImplementedError

    def save_feedback(self, collection_name: str, document: Dict[str, Any]) -> None:
        raise NotImplementedError

    def count_feedback_signals(self, owner_key: str, signal_key: str) -> int:
        raise NotImplementedError

    def list_feedback_documents(
        self,
        owner_key: str,
        signal_key: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def save_checkpoint(self, document: Dict[str, Any]) -> None:
        raise NotImplementedError

    def get_latest_checkpoint(
        self,
        conversation_id: str,
        request_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class AsyncConversationPersistence:
    """Bounded async boundary around the synchronous conversation store.

    PyMongo and the in-memory test store keep their existing synchronous
    contracts. Calls from the async graph are dispatched here so a delayed
    database operation cannot block the event loop. The semaphore bounds both
    active worker calls and submissions to asyncio's shared thread executor.
    """

    def __init__(self, store: BaseConversationStore, max_concurrency: int):
        self._store = store
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def call(self, operation: Callable[..., T], *args: Any) -> T:
        """Run one synchronous persistence operation without blocking the loop."""
        async with self._semaphore:
            return await asyncio.to_thread(operation, *args)

    async def load_context(self, conversation_id: str, recent_limit: int) -> Dict[str, Any]:
        return await self.call(self._store.load_context, conversation_id, recent_limit)

    async def save_thread(self, document: Dict[str, Any]) -> None:
        await self.call(self._store.save_thread, document)

    async def save_turn(self, document: Dict[str, Any]) -> None:
        await self.call(self._store.save_turn, document)

    async def save_summary(self, document: Dict[str, Any]) -> None:
        await self.call(self._store.save_summary, document)

    async def save_answer_review(self, document: Dict[str, Any]) -> None:
        await self.call(self._store.save_answer_review, document)

    async def save_checkpoint(self, document: Dict[str, Any]) -> None:
        await self.call(self._store.save_checkpoint, document)

    async def get_latest_checkpoint(
        self,
        conversation_id: str,
        request_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return await self.call(
            self._store.get_latest_checkpoint,
            conversation_id,
            request_id,
        )


class InMemoryConversationStore(BaseConversationStore):
    """Test-friendly in-memory persistence."""

    def __init__(self, config: Optional[RAGConfig] = None):
        self.config = config or RAGConfig(conversation_store_type="in_memory")
        self.threads: Dict[str, Dict[str, Any]] = {}
        self.turns: Dict[str, Dict[str, Any]] = {}
        self.summaries: Dict[str, Dict[str, Any]] = {}
        self.checkpoints: List[Dict[str, Any]] = []
        self.answer_reviews: Dict[str, Dict[str, Any]] = {}
        self.user_feedback: List[Dict[str, Any]] = []
        self.flow_feedback: List[Dict[str, Any]] = []

    def load_context(self, conversation_id: str, recent_limit: int) -> Dict[str, Any]:
        turns = [
            turn for turn in self.turns.values()
            if turn.get("conversation_id") == conversation_id and self._visible(turn)
        ]
        turns.sort(key=lambda item: item.get("created_at", ""))
        recent_messages: List[Dict[str, Any]] = []
        for turn in turns[-recent_limit:]:
            recent_messages.append({"role": "user", "content": turn.get("user_message", "")})
            recent_messages.append({"role": "assistant", "content": turn.get("final_answer", "")})
        summary = self.summaries.get(_memory_key(conversation_id), {})
        return {
            "thread": copy.deepcopy(self.threads.get(_memory_key(conversation_id), {})),
            "summary": copy.deepcopy(summary.get("summary", "")),
            "recent_messages": recent_messages[-recent_limit:],
        }

    def save_thread(self, document: Dict[str, Any]) -> None:
        self.threads[_memory_key(document["conversation_id"])] = copy.deepcopy(_owned_document(document))

    def save_turn(self, document: Dict[str, Any]) -> None:
        self.turns[_memory_key(document["turn_id"])] = copy.deepcopy(_owned_document(document))

    def save_summary(self, document: Dict[str, Any]) -> None:
        self.summaries[_memory_key(document["conversation_id"])] = copy.deepcopy(_owned_document(document))

    def save_answer_review(self, document: Dict[str, Any]) -> None:
        self.answer_reviews[_memory_key(document["review_id"])] = copy.deepcopy(_owned_document(document))

    def save_feedback(self, collection_name: str, document: Dict[str, Any]) -> None:
        payload = copy.deepcopy(_owned_document(document))
        if collection_name == self.config.user_feedback_collection:
            self.user_feedback.append(payload)
        else:
            self.flow_feedback.append(payload)

    def count_feedback_signals(self, owner_key: str, signal_key: str) -> int:
        turns = {
            doc["turn_id"]
            for doc in (self.user_feedback + self.flow_feedback)
            if doc.get("owner_key") == owner_key and doc.get("memory_signal") == signal_key and self._visible(doc)
        }
        return len(turns)

    def list_feedback_documents(
        self,
        owner_key: str,
        signal_key: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        matches = [
            copy.deepcopy(doc)
            for doc in (self.user_feedback + self.flow_feedback)
            if doc.get("owner_key") == owner_key and doc.get("memory_signal") == signal_key and self._visible(doc)
        ]
        matches.sort(key=lambda item: item.get("created_at", ""))
        return matches[:limit]

    def save_checkpoint(self, document: Dict[str, Any]) -> None:
        self.checkpoints.append(copy.deepcopy(_owned_document(document)))

    def get_latest_checkpoint(
        self,
        conversation_id: str,
        request_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        matches = [
            item for item in self.checkpoints
            if item.get("conversation_id") == conversation_id
            and (request_id is None or item.get("request_id") == request_id)
            and self._visible(item)
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: item.get("created_at", ""))
        return copy.deepcopy(matches[-1])

    @staticmethod
    def _visible(document: Dict[str, Any]) -> bool:
        ownership = _ownership()
        return not ownership or all(document.get(key) == value for key, value in ownership.items() if key != "owner_admin_id")


class MongoConversationStore(BaseConversationStore):
    """MongoDB-backed persistence for production chat state."""

    def __init__(self, config: RAGConfig):
        if not _HAS_PYMONGO:
            raise RuntimeError("pymongo is required for MongoConversationStore")
        self.config = config
        self._client: Optional[MongoClient] = None
        self._db = None

    def _init_db(self) -> None:
        if self._db is not None:
            return
        last_error: Optional[Exception] = None
        for _ in range(self.config.mongodb_max_retries):
            try:
                self._client = MongoClient(self.config.mongodb_url)
                self._db = self._client[self.config.mongodb_database]
                return
            except Exception as exc:  # pragma: no cover - depends on env
                last_error = exc
                time.sleep(self.config.mongodb_retry_delay)
        raise RuntimeError(f"Failed to initialize MongoDB: {last_error}")

    def is_available(self) -> bool:
        """Probe MongoDB so readiness follows dependency failure and recovery."""
        try:
            self._init_db()
            return bool(self._client.admin.command("ping").get("ok"))
        except Exception:
            return False

    def _collection(self, name: str) -> Collection:
        self._init_db()
        return self._db[name]

    def ensure_indexes(self) -> None:
        self._collection(self.config.conversation_threads_collection).create_index(
            [("tenant_id", 1), ("owner_user_id", 1), ("conversation_id", 1)],
            unique=True,
            name="idx_tenant_conversation_id_v2",
        )
        self._collection(self.config.conversation_turns_collection).create_index(
            [("tenant_id", 1), ("owner_user_id", 1), ("conversation_id", 1), ("created_at", -1)],
            name="idx_tenant_turn_conversation_created_v2",
        )
        self._collection(self.config.conversation_turns_collection).create_index(
            [("tenant_id", 1), ("owner_user_id", 1), ("turn_id", 1)],
            unique=True,
            name="idx_tenant_turn_id_v2",
        )
        self._collection(self.config.conversation_summaries_collection).create_index(
            [("tenant_id", 1), ("owner_user_id", 1), ("conversation_id", 1)],
            unique=True,
            name="idx_tenant_summary_conversation_id_v2",
        )
        self._collection(self.config.graph_checkpoints_collection).create_index(
            [("tenant_id", 1), ("owner_user_id", 1), ("conversation_id", 1), ("request_id", 1), ("created_at", -1)],
            name="idx_tenant_checkpoint_lookup_v2",
        )
        self._collection(self.config.graph_checkpoints_collection).create_index(
            [("tenant_id", 1), ("owner_user_id", 1), ("graph_run_id", 1), ("created_at", -1)],
            name="idx_tenant_checkpoint_graph_run_created_v2",
        )
        self._collection(self.config.answer_reviews_collection).create_index(
            [("tenant_id", 1), ("owner_user_id", 1), ("review_id", 1)],
            unique=True,
            name="idx_tenant_review_id_v2",
        )
        self._collection(self.config.user_feedback_collection).create_index(
            [("tenant_id", 1), ("owner_user_id", 1), ("owner_key", 1), ("owner_type", 1), ("memory_signal", 1), ("created_at", -1)],
            name="idx_tenant_feedback_owner_signal_v2",
        )
        self._collection(self.config.flow_feedback_collection).create_index(
            [("tenant_id", 1), ("owner_user_id", 1), ("conversation_id", 1), ("created_at", -1)],
            name="idx_tenant_flow_feedback_conversation_created_v2",
        )

    def load_context(self, conversation_id: str, recent_limit: int) -> Dict[str, Any]:
        turns_cursor = self._collection(self.config.conversation_turns_collection).find(
            _scope({"conversation_id": conversation_id})
        ).sort("created_at", -1).limit(max(recent_limit, 1))
        turns = list(reversed(list(turns_cursor)))
        recent_messages: List[Dict[str, Any]] = []
        for turn in turns:
            recent_messages.append({"role": "user", "content": turn.get("user_message", "")})
            recent_messages.append({"role": "assistant", "content": turn.get("final_answer", "")})
        summary = self._collection(self.config.conversation_summaries_collection).find_one(
            _scope({"conversation_id": conversation_id})
        ) or {}
        thread = self._collection(self.config.conversation_threads_collection).find_one(
            _scope({"conversation_id": conversation_id})
        ) or {}
        return {
            "thread": make_json_safe(thread),
            "summary": summary.get("summary", ""),
            "recent_messages": recent_messages[-recent_limit:],
        }

    def save_thread(self, document: Dict[str, Any]) -> None:
        payload = _owned_document(document)
        self._collection(self.config.conversation_threads_collection).update_one(
            _scope({"conversation_id": payload["conversation_id"]}),
            {"$set": payload},
            upsert=True,
        )

    def save_turn(self, document: Dict[str, Any]) -> None:
        payload = _owned_document(document)
        self._collection(self.config.conversation_turns_collection).update_one(
            _scope({"turn_id": payload["turn_id"]}),
            {"$set": payload},
            upsert=True,
        )

    def save_summary(self, document: Dict[str, Any]) -> None:
        payload = _owned_document(document)
        self._collection(self.config.conversation_summaries_collection).update_one(
            _scope({"conversation_id": payload["conversation_id"]}),
            {"$set": payload},
            upsert=True,
        )

    def save_answer_review(self, document: Dict[str, Any]) -> None:
        payload = _owned_document(document)
        self._collection(self.config.answer_reviews_collection).update_one(
            _scope({"review_id": payload["review_id"]}),
            {"$set": payload},
            upsert=True,
        )

    def save_feedback(self, collection_name: str, document: Dict[str, Any]) -> None:
        self._collection(collection_name).insert_one(_owned_document(document))

    def count_feedback_signals(self, owner_key: str, signal_key: str) -> int:
        pipeline = [
            {"$match": _scope({"owner_key": owner_key, "memory_signal": signal_key})},
            {"$group": {"_id": "$turn_id"}},
        ]
        turn_ids = set()
        for collection_name in [self.config.user_feedback_collection, self.config.flow_feedback_collection]:
            rows = list(self._collection(collection_name).aggregate(pipeline))
            turn_ids.update(str(row["_id"]) for row in rows)
        return len(turn_ids)

    def list_feedback_documents(
        self,
        owner_key: str,
        signal_key: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        query = _scope({"owner_key": owner_key, "memory_signal": signal_key})
        for collection_name in [self.config.user_feedback_collection, self.config.flow_feedback_collection]:
            rows = list(
                self._collection(collection_name)
                .find(query)
                .sort("created_at", 1)
            )
            matches.extend(make_json_safe(row) for row in rows)
        matches.sort(key=lambda item: item.get("created_at", ""))
        return matches[:limit]

    def save_checkpoint(self, document: Dict[str, Any]) -> None:
        self._collection(self.config.graph_checkpoints_collection).insert_one(
            _owned_document(document)
        )

    def get_latest_checkpoint(
        self,
        conversation_id: str,
        request_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        query: Dict[str, Any] = {"conversation_id": conversation_id}
        if request_id is not None:
            query["request_id"] = request_id
        checkpoint = self._collection(self.config.graph_checkpoints_collection).find_one(
            _scope(query),
            sort=[("created_at", -1)],
        )
        return make_json_safe(checkpoint) if checkpoint else None


def create_conversation_store(config: RAGConfig) -> BaseConversationStore:
    """Create the configured conversation store."""
    if config.conversation_store_type.lower() == "in_memory":
        return InMemoryConversationStore(config)
    return MongoConversationStore(config)
