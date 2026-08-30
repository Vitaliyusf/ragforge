"""Long-term memory domain service backed by MongoDB."""
from __future__ import annotations

import copy
import hashlib
import math
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from pymongo.collection import Collection

from app.core.config import settings
from app.core.errors import DatabaseError
from shared.logging import ServiceLogger
from shared.metrics import METRICS
from app.db.session import get_db
from app.services.memory_embedding_client import MemoryEmbeddingClient, MemoryEmbeddingError
from app.services.memory_vector_index import MemoryVectorIndex, MemoryVectorIndexError
from app.services.tenant_scope import current_identity, ownership_fields, scope_filter


ALLOWED_OWNER_TYPES = {"user", "session", "conversation"}
ALLOWED_MEMORY_CLASSES = {"episodic", "semantic_preference"}

# Memory lifecycle. Exactly one of these is authoritative for a given fact:
# `active`. `superseded` and `archived` stay readable for history and audit but
# never answer a current-fact query; `deleted` is a tombstone that exists only
# until the vector index has confirmed the point is gone.
MEMORY_STATUS_ACTIVE = "active"
MEMORY_STATUS_SUPERSEDED = "superseded"
MEMORY_STATUS_ARCHIVED = "archived"
MEMORY_STATUS_DELETED = "deleted"
RETRIEVABLE_STATUSES = {MEMORY_STATUS_ACTIVE}

# Vector synchronisation state. MongoDB is the canonical store and the vector
# index is derived, so a divergence is recorded rather than hidden: anything
# other than `indexed`/`disabled` is a reconciliation obligation.
EMBEDDING_STATUS_DISABLED = "disabled"
EMBEDDING_STATUS_INDEXED = "indexed"
EMBEDDING_STATUS_PENDING = "pending"
EMBEDDING_STATUS_FAILED = "failed"
EMBEDDING_STATUS_DELETE_PENDING = "delete_pending"
RECONCILIATION_STATUSES = {
    EMBEDDING_STATUS_PENDING,
    EMBEDDING_STATUS_FAILED,
    EMBEDDING_STATUS_DELETE_PENDING,
}

# Bounded failure classes for metrics labels — never a raw exception string.
FAILURE_CLASS_EMBEDDING = "embedding"
FAILURE_CLASS_VECTOR_INDEX = "vector_index"
FAILURE_CLASS_DATABASE = "database"
FAILURE_CLASS_VALIDATION = "validation"


def _utc_now() -> str:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse timestamp-like values safely."""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class LongTermMemoryService:
    """Mongo-backed long-term memory service."""

    def __init__(
        self,
        logger: ServiceLogger,
        db_provider: Optional[Callable[[], Any]] = None,
        index_client: Optional[MemoryVectorIndex] = None,
        now_fn: Optional[Callable[[], str]] = None,
        embedding_client: Optional[MemoryEmbeddingClient] = None,
    ):
        self.logger = logger
        self._db_provider = db_provider or get_db
        self._index_client = index_client or MemoryVectorIndex(logger)
        self._embedding_client = embedding_client or MemoryEmbeddingClient(logger)
        self._now_fn = now_fn or _utc_now
        self._indexes_ready = False

    def _db(self) -> Any:
        """Return the configured database handle."""
        return self._db_provider()

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def _record_operation(self, operation: str) -> None:
        """Count one memory operation. Labels stay a fixed, small set."""
        METRICS.memory_operations_total.labels(
            service=settings.service_name,
            operation=operation,
        ).inc()

    def _record_duration(self, operation: str, started: float) -> None:
        """Observe how long one memory operation took."""
        METRICS.memory_operation_duration.labels(
            service=settings.service_name,
            operation=operation,
        ).observe(time.monotonic() - started)

    def _record_failure(self, operation: str, failure_class: str) -> None:
        """Count one failed memory operation by bounded failure class."""
        METRICS.memory_operation_failures_total.labels(
            service=settings.service_name,
            operation=operation,
            failure_class=failure_class,
        ).inc()

    def index_provenance(self) -> Dict[str, Any]:
        """Return the runtime evidence describing the active retrieval path."""
        return {
            "implementation": "app.services.memory_service.LongTermMemoryService",
            "persistence": "mongodb",
            "vector_index": {
                "enabled": self._index_client.is_enabled(),
                "collection": getattr(self._index_client, "collection_name", None),
            },
            "embedding": self._embedding_client.provenance(),
        }

    def _episodic_collection(self) -> Collection:
        """Return episodic memories collection."""
        return self._db()["episodic_memories"]

    def _semantic_collection(self) -> Collection:
        """Return semantic preferences collection."""
        return self._db()["semantic_preferences"]

    def _write_log_collection(self) -> Collection:
        """Return write log collection."""
        return self._db()["memory_write_log"]

    def _ensure_indexes(self) -> None:
        """Create Mongo indexes used by the memory service."""
        if self._indexes_ready:
            return
        try:
            self._episodic_collection().create_index(
                [("tenant_id", 1), ("owner_user_id", 1), ("owner_id", 1), ("owner_type", 1), ("archived_at", 1), ("updated_at", -1)]
            )
            self._episodic_collection().create_index(
                [("tenant_id", 1), ("owner_user_id", 1), ("owner_id", 1), ("owner_type", 1), ("importance", -1)]
            )
            self._episodic_collection().create_index(
                [("tenant_id", 1), ("owner_user_id", 1), ("owner_id", 1), ("owner_type", 1), ("event_at", -1)]
            )
            self._episodic_collection().create_index(
                [("tenant_id", 1), ("owner_user_id", 1), ("owner_id", 1), ("owner_type", 1), ("status", 1)]
            )
            self._episodic_collection().create_index(
                [("tenant_id", 1), ("owner_user_id", 1), ("content_hash", 1)]
            )
            self._episodic_collection().create_index([("tags", 1)])
            self._semantic_collection().create_index(
                [("tenant_id", 1), ("owner_user_id", 1), ("owner_id", 1), ("owner_type", 1), ("status", 1)]
            )
            self._semantic_collection().create_index(
                [("tenant_id", 1), ("owner_user_id", 1), ("content_hash", 1)]
            )
            self._semantic_collection().create_index(
                [("tenant_id", 1), ("owner_user_id", 1), ("owner_id", 1), ("owner_type", 1), ("preference_key", 1)],
                unique=True,
            )
            self._semantic_collection().create_index(
                [("tenant_id", 1), ("owner_user_id", 1), ("owner_id", 1), ("owner_type", 1), ("archived_at", 1), ("updated_at", -1)]
            )
            self._write_log_collection().create_index(
                [("request_id", 1)],
                unique=True,
                sparse=True,
            )
            self._write_log_collection().create_index(
                [("tenant_id", 1), ("owner_user_id", 1), ("owner_id", 1), ("owner_type", 1), ("created_at", -1)]
            )
            self._write_log_collection().create_index([("status", 1), ("created_at", -1)])
            self._indexes_ready = True
        except Exception as exc:
            self.logger.log(
                "memory_service:indexes",
                "Failed to ensure indexes",
                {"error": str(exc)},
                "E",
            )

    def _coerce_float(self, value: Any, default: float) -> float:
        """Coerce values to floats within [0, 1]."""
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default

    def _coerce_int(self, value: Any, default: int) -> int:
        """Coerce values to ints safely."""
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    def _normalize_text(self, value: Any) -> str:
        """Normalize free-form text."""
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def _as_string_list(self, value: Any) -> List[str]:
        """Normalize tags and keyword lists."""
        if value is None:
            return []
        if isinstance(value, str):
            parts = re.split(r"[,|]", value)
        elif isinstance(value, (list, tuple, set)):
            parts = list(value)
        else:
            parts = [value]

        seen: List[str] = []
        for item in parts:
            normalized = self._normalize_text(item).lower()
            if normalized and normalized not in seen:
                seen.append(normalized)
        return seen

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into lightweight keywords."""
        return list(dict.fromkeys(re.findall(r"[a-z0-9_+-]+", text.lower())))

    def _content_hash(self, owner_id: str, owner_type: str, memory_class: str, text: str) -> str:
        """Return the deterministic identity of one memory's normalized content.

        Exact-duplicate detection has to survive casing and whitespace noise,
        so identity is computed from the same normalized text that is stored,
        lowercased, and scoped to the owner and memory class.
        """
        material = "|".join([owner_id, owner_type, memory_class, text.strip().lower()])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _build_summary(self, text: str) -> str:
        """Create a short summary from the main text."""
        if len(text) <= 160:
            return text
        return f"{text[:157].rstrip()}..."

    def _normalize_provenance(
        self,
        provenance: Any,
        request_context: Dict[str, Any],
        candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Keep only provenance fields safe to store."""
        raw = provenance if isinstance(provenance, dict) else {}
        result: Dict[str, Any] = {}
        allowed_keys = {
            "chat_id",
            "conversation_id",
            "message_id",
            "message_ids",
            "event_at",
            "explicit_user_signal",
            "stable_feedback_count",
            "source_type",
            "hidden_reasoning",
            "raw_retrieval_dump",
            "raw_transcript",
        }
        for key in allowed_keys:
            if key in raw:
                result[key] = copy.deepcopy(raw[key])

        for key in ("chat_id", "conversation_id", "message_id"):
            if key in candidate and key not in result:
                result[key] = candidate[key]

        if request_context.get("trace_id") and "trace_id" not in result:
            result["trace_id"] = request_context["trace_id"]

        message_ids = result.get("message_ids")
        if message_ids is not None and not isinstance(message_ids, list):
            result["message_ids"] = [message_ids]

        return result

    def _classify_candidate(self, candidate: Dict[str, Any], text: str) -> str:
        """Infer memory class when not explicit."""
        explicit_class = self._normalize_text(candidate.get("memory_class")).lower()
        if explicit_class in ALLOWED_MEMORY_CLASSES:
            return explicit_class

        category = self._normalize_text(candidate.get("category")).lower()
        if candidate.get("preference_key") or candidate.get("value") is not None:
            return "semantic_preference"
        if "preference" in category:
            return "semantic_preference"

        text_lower = text.lower()
        preference_markers = (
            "prefer concise",
            "prefer detailed",
            "prefers concise",
            "prefers detailed",
            "prefer citations",
            "prefers citations",
            "use bullet",
            "use markdown",
            "format answers",
        )
        if any(marker in text_lower for marker in preference_markers):
            return "semantic_preference"

        return "episodic"

    def _infer_preference_key(self, text: str, tags: List[str]) -> str:
        """Infer a preference key from text."""
        lower = text.lower()
        if "citation" in lower or "cite" in lower:
            return "citations"
        if "bullet" in lower or "markdown" in lower or "format" in lower:
            return "formatting_style"
        if "concise" in lower or "brief" in lower or "extended" in lower or "detailed" in lower:
            return "response_style"
        if "tone" in lower:
            return "tone"
        if tags:
            return tags[0]
        return "communication_preference"

    def _infer_preference_value(self, preference_key: str, text: str) -> Any:
        """Infer a preference value from text."""
        lower = text.lower()
        if preference_key == "citations":
            return "required" if ("citation" in lower or "cite" in lower) else "preferred"
        if preference_key == "response_style":
            if "concise" in lower or "brief" in lower:
                return "concise"
            if "extended" in lower or "detailed" in lower:
                return "extended"
        if preference_key == "formatting_style":
            if "bullet" in lower:
                return "bullets"
            if "markdown" in lower:
                return "markdown"
        return self._build_summary(text)

    def _infer_value_type(self, value: Any) -> str:
        """Infer a stored preference value type."""
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        return "string"

    def _normalize_candidate(
        self,
        candidate: Optional[Dict[str, Any]],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Normalize write candidates to canonical memory shape."""
        request_context = request_context or {}
        candidate = copy.deepcopy(candidate or {})
        content = candidate.get("content", {})

        if isinstance(content, dict):
            raw_text = content.get("text") or candidate.get("text") or ""
            summary = content.get("summary") or candidate.get("summary") or ""
        elif isinstance(content, str):
            raw_text = content
            summary = candidate.get("summary") or ""
        else:
            raw_text = candidate.get("text") or ""
            summary = candidate.get("summary") or ""

        text = self._normalize_text(raw_text)
        memory_class = self._classify_candidate(candidate, text)
        identity = current_identity()
        owner_id = self._normalize_text(
            identity.user_id if identity is not None else candidate.get("owner_id") or request_context.get("owner_id")
        )
        owner_type = self._normalize_text(
            "user" if identity is not None else candidate.get("owner_type") or request_context.get("owner_type") or "user"
        ).lower()

        provenance = self._normalize_provenance(candidate.get("provenance"), request_context, candidate)
        tags = self._as_string_list(candidate.get("tags"))
        retrieval = candidate.get("retrieval", {}) if isinstance(candidate.get("retrieval"), dict) else {}
        keywords = self._as_string_list(retrieval.get("keywords") or candidate.get("keywords"))
        if not keywords:
            keywords = self._as_string_list(tags + self._tokenize(f"{text} {summary}")[:12])

        explicit_signal = bool(provenance.get("explicit_user_signal"))
        stable_feedback_count = self._coerce_int(provenance.get("stable_feedback_count"), 0)
        default_confidence = 0.8 if explicit_signal else 0.6
        default_importance = 0.8 if memory_class == "semantic_preference" else 0.65
        now = self._now_fn()

        normalized: Dict[str, Any] = {
            "id": self._normalize_text(candidate.get("id")) or str(uuid.uuid4()),
            "owner_id": owner_id,
            "owner_type": owner_type,
            "memory_class": memory_class,
            "content": {
                "text": text,
                "summary": self._normalize_text(summary) or self._build_summary(text),
            },
            "source": candidate.get("source") or request_context.get("source") or provenance.get("source_type") or "unknown",
            "confidence": self._coerce_float(candidate.get("confidence"), default_confidence),
            "importance": self._coerce_float(candidate.get("importance"), default_importance),
            "tags": tags,
            "created_at": candidate.get("created_at") or now,
            "updated_at": candidate.get("updated_at") or now,
            "last_accessed_at": candidate.get("last_accessed_at"),
            "archived_at": candidate.get("archived_at"),
            "status": MEMORY_STATUS_ACTIVE,
            "revision": max(1, self._coerce_int(candidate.get("revision"), 1)),
            "supersedes": self._normalize_text(candidate.get("supersedes")) or None,
            "superseded_by": None,
            "content_hash": self._content_hash(owner_id, owner_type, memory_class, text),
            "provenance": provenance,
            "retrieval": {
                "keywords": keywords,
                "embedding_status": retrieval.get("embedding_status")
                or (
                    EMBEDDING_STATUS_PENDING
                    if self._index_client.is_enabled()
                    else EMBEDDING_STATUS_DISABLED
                ),
                "qdrant_point_id": retrieval.get("qdrant_point_id"),
                "embedding_model": None,
                "embedding_dimensions": None,
                "vector_collection": None,
                "vector_synced_at": None,
            },
            **ownership_fields(),
        }

        if memory_class == "semantic_preference":
            preference_key = self._normalize_text(
                candidate.get("preference_key") or self._infer_preference_key(text, tags)
            ).lower()
            value = candidate.get("value")
            if value is None:
                value = self._infer_preference_value(preference_key, text)
            normalized.update(
                {
                    "preference_key": preference_key,
                    "value": value,
                    "value_type": candidate.get("value_type") or self._infer_value_type(value),
                    "strength": self._coerce_float(
                        candidate.get("strength"),
                        max(normalized["confidence"], 0.65),
                    ),
                    "evidence_count": max(
                        self._coerce_int(candidate.get("evidence_count"), stable_feedback_count),
                        1 if explicit_signal else stable_feedback_count,
                    ),
                }
            )
            if not normalized["content"]["text"] and preference_key:
                normalized["content"]["text"] = f"Preference {preference_key}: {value}"
                normalized["content"]["summary"] = self._build_summary(normalized["content"]["text"])
        else:
            normalized.update(
                {
                    "event_at": candidate.get("event_at") or provenance.get("event_at") or now,
                    "expires_at": candidate.get("expires_at"),
                    "stability": self._coerce_float(
                        candidate.get("stability"),
                        max(normalized["confidence"], 0.55),
                    ),
                }
            )

        return normalized

    def _first_failed_reason(self, checks: List[Tuple[str, bool, str]]) -> str:
        """Return the first failure reason from ordered policy checks."""
        for _, passed, reason in checks:
            if not passed:
                return reason
        return "accepted"

    def _looks_like_transcript(self, text: str) -> bool:
        """Heuristic to reject raw transcript dumps."""
        lowered = text.lower()
        return lowered.count("user:") >= 1 and lowered.count("assistant:") >= 1

    def _looks_like_retrieval_dump(self, text: str, normalized: Dict[str, Any]) -> bool:
        """Heuristic to reject raw retrieval or document dumps."""
        lowered = text.lower()
        if normalized["provenance"].get("raw_retrieval_dump"):
            return True
        markers = ("page_content", "document:", "chunk", "retrieval result", "embedding score")
        return any(marker in lowered for marker in markers)

    def _looks_like_hidden_reasoning(self, text: str, normalized: Dict[str, Any]) -> bool:
        """Heuristic to reject hidden reasoning traces."""
        lowered = text.lower()
        if normalized["provenance"].get("hidden_reasoning"):
            return True
        markers = ("chain of thought", "hidden reasoning", "reasoning trace", "internal scratchpad")
        return any(marker in lowered for marker in markers)

    def _looks_like_temporary_state(self, text: str) -> bool:
        """Heuristic to reject temporary task state."""
        lowered = text.lower()
        markers = (
            "for this session",
            "for now",
            "currently working on",
            "temporary",
            "todo",
            "next turn",
            "draft",
            "in progress",
        )
        return any(marker in lowered for marker in markers)

    def _evaluate_write_policy(self, normalized: Dict[str, Any]) -> Tuple[bool, Dict[str, bool], str]:
        """Apply durable-memory policy checks."""
        text = normalized["content"]["text"]
        explicit_signal = bool(normalized["provenance"].get("explicit_user_signal"))
        stable_feedback = self._coerce_int(normalized["provenance"].get("stable_feedback_count"), 0)
        preference_signal = explicit_signal or stable_feedback >= 2 or normalized.get("evidence_count", 0) >= 2

        ordered_checks = [
            ("owner_id", bool(normalized["owner_id"]), "owner_id is required"),
            ("owner_type", normalized["owner_type"] in ALLOWED_OWNER_TYPES, "owner_type is invalid"),
            ("text", bool(text), "memory text is required"),
            ("not_transcript", not self._looks_like_transcript(text), "raw transcript dumps are not stored"),
            (
                "not_retrieval_dump",
                not self._looks_like_retrieval_dump(text, normalized),
                "raw retrieval dumps are not stored",
            ),
            (
                "not_hidden_reasoning",
                not self._looks_like_hidden_reasoning(text, normalized),
                "hidden reasoning is not stored",
            ),
            (
                "not_temporary_state",
                not self._looks_like_temporary_state(text),
                "temporary task state is not stored",
            ),
            ("confidence", normalized["confidence"] >= 0.35, "candidate confidence is too low"),
            ("importance", normalized["importance"] >= 0.35, "candidate importance is too low"),
        ]

        if normalized["memory_class"] == "semantic_preference":
            ordered_checks.extend(
                [
                    ("preference_key", bool(normalized.get("preference_key")), "preference_key is required"),
                    ("preference_value", normalized.get("value") not in (None, ""), "preference value is required"),
                    (
                        "preference_signal",
                        preference_signal,
                        "semantic preferences require explicit signal or repeated stable feedback",
                    ),
                ]
            )
        else:
            ordered_checks.append(("event_at", bool(normalized.get("event_at")), "event_at is required"))

        checks = {name: passed for name, passed, _ in ordered_checks}
        accepted = all(checks.values())
        return accepted, checks, self._first_failed_reason(ordered_checks)

    def _safe_provenance(self, provenance: Any) -> Dict[str, Any]:
        """Limit provenance fields returned in retrieval/debug responses."""
        if not isinstance(provenance, dict):
            return {}
        allowed_keys = {"chat_id", "conversation_id", "message_id", "message_ids", "source_type", "explicit_user_signal"}
        return {key: copy.deepcopy(value) for key, value in provenance.items() if key in allowed_keys}

    def _normalize_output_memory(self, doc: Dict[str, Any], ranking: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Normalize stored documents for memory retrieval responses."""
        result = {
            "id": doc["id"],
            "owner_id": doc["owner_id"],
            "owner_type": doc["owner_type"],
            "memory_class": doc["memory_class"],
            "content": copy.deepcopy(doc.get("content", {})),
            "source": copy.deepcopy(doc.get("source")),
            "confidence": doc.get("confidence"),
            "importance": doc.get("importance"),
            "tags": copy.deepcopy(doc.get("tags", [])),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
            "last_accessed_at": doc.get("last_accessed_at"),
            "archived_at": doc.get("archived_at"),
            "status": doc.get("status", MEMORY_STATUS_ACTIVE),
            "revision": doc.get("revision", 1),
            "supersedes": doc.get("supersedes"),
            "superseded_by": doc.get("superseded_by"),
            "provenance": self._safe_provenance(doc.get("provenance")),
            "retrieval": {
                "keywords": copy.deepcopy(doc.get("retrieval", {}).get("keywords", [])),
                "embedding_status": doc.get("retrieval", {}).get("embedding_status"),
                "qdrant_point_id": doc.get("retrieval", {}).get("qdrant_point_id"),
                "embedding_model": doc.get("retrieval", {}).get("embedding_model"),
                "embedding_dimensions": doc.get("retrieval", {}).get("embedding_dimensions"),
                "vector_collection": doc.get("retrieval", {}).get("vector_collection"),
                "vector_synced_at": doc.get("retrieval", {}).get("vector_synced_at"),
            },
        }
        if doc["memory_class"] == "episodic":
            result["event_at"] = doc.get("event_at")
            result["expires_at"] = doc.get("expires_at")
            result["stability"] = doc.get("stability")
        else:
            result["preference_key"] = doc.get("preference_key")
            result["value"] = copy.deepcopy(doc.get("value"))
            result["value_type"] = doc.get("value_type")
            result["strength"] = doc.get("strength")
            result["evidence_count"] = doc.get("evidence_count")
        if ranking is not None:
            result["ranking"] = ranking
        return result

    def _to_legacy_memory(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten canonical documents for legacy callers."""
        legacy = {
            "id": doc["id"],
            "content": doc.get("content", {}).get("text", ""),
            "category": doc["memory_class"],
            "metadata": {
                "owner_id": doc.get("owner_id"),
                "owner_type": doc.get("owner_type"),
                "source": doc.get("source"),
                "tags": copy.deepcopy(doc.get("tags", [])),
                "provenance": self._safe_provenance(doc.get("provenance")),
            },
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        }
        if doc["memory_class"] == "semantic_preference":
            legacy["metadata"]["preference_key"] = doc.get("preference_key")
            legacy["metadata"]["value"] = copy.deepcopy(doc.get("value"))
        return legacy

    def _all_memory_documents(self, include_tombstones: bool = False) -> List[Dict[str, Any]]:
        """Return canonical memory documents across collections.

        Tombstones are documents whose delete has been accepted but whose
        vector point is not confirmed gone yet. They are invisible to every
        caller except reconciliation.
        """
        episodic = list(self._episodic_collection().find(scope_filter(), {"_id": 0}))
        semantic = list(self._semantic_collection().find(scope_filter(), {"_id": 0}))
        documents = episodic + semantic
        if include_tombstones:
            return documents
        return [doc for doc in documents if doc.get("status") != MEMORY_STATUS_DELETED]

    def _memory_status(self, doc: Dict[str, Any]) -> str:
        """Return a document's lifecycle status.

        Documents written before the status field existed are `active` unless
        they carry an `archived_at`, which is how archival used to be encoded.
        """
        status = doc.get("status")
        if status:
            return str(status)
        return MEMORY_STATUS_ARCHIVED if doc.get("archived_at") else MEMORY_STATUS_ACTIVE

    def _active_memory_documents(
        self,
        owner_id: Optional[str] = None,
        owner_type: Optional[str] = None,
        memory_classes: Optional[List[str]] = None,
        include_archived: bool = False,
    ) -> List[Dict[str, Any]]:
        """Filter canonical memory documents in Python to keep fake-test support simple."""
        classes = set(memory_classes or ALLOWED_MEMORY_CLASSES)
        documents: List[Dict[str, Any]] = []
        for doc in self._all_memory_documents():
            if doc.get("memory_class") not in classes:
                continue
            if owner_id and doc.get("owner_id") != owner_id:
                continue
            if owner_type and doc.get("owner_type") != owner_type:
                continue
            if not include_archived and doc.get("archived_at"):
                continue
            if not include_archived and self._memory_status(doc) not in RETRIEVABLE_STATUSES:
                continue
            documents.append(doc)
        return documents

    def _find_active_duplicate(self, normalized: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return an existing active memory with identical normalized content."""
        for doc in self._active_memory_documents(
            owner_id=normalized["owner_id"],
            owner_type=normalized["owner_type"],
            memory_classes=[normalized["memory_class"]],
            include_archived=False,
        ):
            if doc.get("content_hash") and doc["content_hash"] == normalized["content_hash"]:
                return doc
        return None

    def _find_memory_document(
        self,
        memory_id: str,
        include_tombstones: bool = False,
    ) -> Tuple[Optional[Collection], Optional[Dict[str, Any]]]:
        """Find a memory by id across both collections, inside the caller's scope."""
        for collection in (self._episodic_collection(), self._semantic_collection()):
            doc = collection.find_one(scope_filter({"id": memory_id}), {"_id": 0})
            if not doc:
                continue
            if not include_tombstones and doc.get("status") == MEMORY_STATUS_DELETED:
                continue
            return collection, doc
        return None, None

    def _text_similarity(self, left_tokens: List[str], right_tokens: List[str]) -> float:
        """Compute Jaccard similarity between token sets."""
        left_set = set(left_tokens)
        right_set = set(right_tokens)
        if not left_set or not right_set:
            return 0.0
        return len(left_set & right_set) / max(len(left_set | right_set), 1)

    def _merge_provenance(self, left: Any, right: Any) -> Dict[str, Any]:
        """Merge provenance dictionaries conservatively."""
        merged: Dict[str, Any] = {}
        if isinstance(left, dict):
            merged.update(copy.deepcopy(left))
        if isinstance(right, dict):
            for key, value in right.items():
                if key == "message_ids":
                    merged[key] = list(
                        dict.fromkeys((merged.get(key) or []) + (value if isinstance(value, list) else [value]))
                    )
                elif key not in merged or merged[key] in (None, "", []):
                    merged[key] = copy.deepcopy(value)
                elif key in {"explicit_user_signal", "raw_transcript", "raw_retrieval_dump", "hidden_reasoning"}:
                    merged[key] = bool(merged[key] or value)
        return merged

    def _find_similar_episodic_memory(self, normalized: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a similar episodic memory to merge with."""
        candidate_tokens = normalized["retrieval"]["keywords"] or self._tokenize(normalized["content"]["text"])
        candidate_time = _parse_datetime(normalized.get("event_at"))
        for existing in self._active_memory_documents(
            owner_id=normalized["owner_id"],
            owner_type=normalized["owner_type"],
            memory_classes=["episodic"],
            include_archived=False,
        ):
            existing_tokens = existing.get("retrieval", {}).get("keywords", []) or self._tokenize(
                existing.get("content", {}).get("text", "")
            )
            similarity = self._text_similarity(candidate_tokens, existing_tokens)
            if similarity < 0.65:
                continue
            existing_time = _parse_datetime(existing.get("event_at"))
            if candidate_time and existing_time:
                day_gap = abs((candidate_time - existing_time).days)
                if day_gap > 30 and similarity < 0.8:
                    continue
            return existing
        return None

    def _persist_memory(self, collection: Collection, doc: Dict[str, Any], is_update: bool) -> Dict[str, Any]:
        """Insert or update a canonical memory document."""
        if is_update:
            collection.update_one(scope_filter({"id": doc["id"]}), {"$set": doc})
        else:
            collection.insert_one({**doc, **ownership_fields()})
        return doc

    def _persist_retrieval_state(self, doc: Dict[str, Any]) -> None:
        """Update retrieval fields after Qdrant sync attempt."""
        collection = self._episodic_collection() if doc["memory_class"] == "episodic" else self._semantic_collection()
        collection.update_one(
            scope_filter({"id": doc["id"]}),
            {
                "$set": {
                    "retrieval": copy.deepcopy(doc["retrieval"]),
                    "updated_at": doc["updated_at"],
                }
            },
        )

    def _sync_vector_index(self, doc: Dict[str, Any]) -> Tuple[Optional[bool], Optional[str]]:
        """Embed one memory and upsert it into the vector index.

        MongoDB already holds the authoritative record by the time this runs,
        so a failure here is not fatal — but it is never hidden: the document
        keeps an explicit ``pending``/``failed`` embedding status that marks it
        as owing reconciliation, and the write result reports it. A vector is
        never synthesised locally when the embedding service is unavailable.
        """
        if not self._index_client.is_enabled():
            doc["retrieval"]["embedding_status"] = EMBEDDING_STATUS_DISABLED
            self._persist_retrieval_state(doc)
            return None, None

        text = doc.get("content", {}).get("text", "")
        try:
            vector = self._embedding_client.embed_memory(text)
        except MemoryEmbeddingError as exc:
            self._record_failure("write_memory", FAILURE_CLASS_EMBEDDING)
            return self._record_vector_failure(doc, EMBEDDING_STATUS_FAILED, str(exc))

        try:
            point_id = self._index_client.upsert_memory(doc, vector)
        except MemoryVectorIndexError as exc:
            self._record_failure("write_memory", FAILURE_CLASS_VECTOR_INDEX)
            return self._record_vector_failure(doc, EMBEDDING_STATUS_PENDING, str(exc))

        doc["retrieval"].update(
            {
                "embedding_status": EMBEDDING_STATUS_INDEXED,
                "qdrant_point_id": point_id,
                "embedding_model": self._embedding_client.model,
                "embedding_dimensions": self._embedding_client.dimensions,
                "vector_collection": self._index_client.collection_name,
                "vector_synced_at": self._now_fn(),
            }
        )
        doc["updated_at"] = self._now_fn()
        self._persist_retrieval_state(doc)
        return True, None

    def _record_vector_failure(
        self,
        doc: Dict[str, Any],
        status: str,
        error: str,
    ) -> Tuple[bool, str]:
        """Persist an explicit reconciliation state after a failed vector sync."""
        doc["retrieval"].update(
            {
                "embedding_status": status,
                "qdrant_point_id": None,
                "embedding_model": self._embedding_client.model,
                "embedding_dimensions": self._embedding_client.dimensions,
                "vector_collection": self._index_client.collection_name,
                "vector_synced_at": None,
            }
        )
        doc["updated_at"] = self._now_fn()
        self._persist_retrieval_state(doc)
        self.logger.log(
            "memory_service:_sync_vector_index",
            "Memory stored without a synchronised vector; reconciliation required",
            {"memory_id": doc.get("id"), "embedding_status": status, "error": error},
            "W",
        )
        return False, error

    def _log_outcome(
        self,
        request_context: Dict[str, Any],
        candidate_snapshot: Dict[str, Any],
        normalized_candidate: Optional[Dict[str, Any]],
        status: str,
        memory_id: Optional[str],
        memory_class: Optional[str],
        reason: str,
        policy_checks: Optional[Dict[str, bool]],
        qdrant_indexed: Optional[bool] = None,
        qdrant_error: Optional[str] = None,
    ) -> None:
        """Write a memory write log entry."""
        request_id = request_context.get("request_id")
        existing = None
        if request_id:
            existing = self._write_log_collection().find_one(scope_filter({"request_id": request_id}), {"_id": 0})
        if existing:
            self._write_log_collection().update_one(
                scope_filter({"id": existing["id"]}),
                {
                    "$set": {
                        "status": status,
                        "memory_id": memory_id,
                        "memory_class": memory_class,
                        "reason": reason,
                        "policy_checks": copy.deepcopy(policy_checks or {}),
                        "qdrant_indexed": qdrant_indexed,
                        "qdrant_error": qdrant_error,
                        "normalized_candidate": copy.deepcopy(normalized_candidate),
                    }
                },
            )
            return

        log_doc = {
            "id": str(uuid.uuid4()),
            "request_id": request_id,
            "trace_id": request_context.get("trace_id"),
            "correlation_id": request_context.get("correlation_id"),
            "owner_id": request_context.get("owner_id"),
            "owner_type": request_context.get("owner_type"),
            "candidate_snapshot": copy.deepcopy(candidate_snapshot),
            "normalized_candidate": copy.deepcopy(normalized_candidate),
            "status": status,
            "memory_id": memory_id,
            "memory_class": memory_class,
            "reason": reason,
            "policy_checks": copy.deepcopy(policy_checks or {}),
            "qdrant_indexed": qdrant_indexed,
            "qdrant_error": qdrant_error,
            "created_at": self._now_fn(),
            **ownership_fields(),
        }
        self._write_log_collection().insert_one(log_doc)

    def _result_from_log(self, log_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a stored log document back into a write result.

        Replaying a logged outcome must report the same reconciliation state
        the original call did, so a retried request_id cannot turn a pending
        vector sync into an apparent success.
        """
        memory_id = log_doc.get("memory_id")
        embedding_status = None
        if memory_id:
            _, doc = self._find_memory_document(memory_id)
            if doc:
                embedding_status = doc.get("retrieval", {}).get("embedding_status")
        return {
            "status": log_doc.get("status"),
            "memory_id": memory_id,
            "memory_class": log_doc.get("memory_class"),
            "reason": log_doc.get("reason"),
            "qdrant_indexed": log_doc.get("qdrant_indexed"),
            "embedding_status": embedding_status,
            "reconciliation_required": embedding_status in RECONCILIATION_STATUSES,
        }

    def _merged_retrieval_state(
        self,
        existing: Dict[str, Any],
        normalized: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Combine keywords and reset vector state after content changed.

        The stored text is about to change, so whatever vector the index holds
        is stale: the merged document goes back to `pending` and is re-embedded
        by the caller.
        """
        existing_retrieval = existing.get("retrieval", {}) or {}
        return {
            "keywords": self._as_string_list(
                existing_retrieval.get("keywords", []) + normalized["retrieval"]["keywords"]
            ),
            "embedding_status": (
                EMBEDDING_STATUS_PENDING
                if self._index_client.is_enabled()
                else EMBEDDING_STATUS_DISABLED
            ),
            "qdrant_point_id": existing_retrieval.get("qdrant_point_id"),
            "embedding_model": existing_retrieval.get("embedding_model"),
            "embedding_dimensions": existing_retrieval.get("embedding_dimensions"),
            "vector_collection": existing_retrieval.get("vector_collection"),
            "vector_synced_at": existing_retrieval.get("vector_synced_at"),
        }

    def _apply_supersession(self, normalized: Dict[str, Any]) -> Optional[str]:
        """Retire the memory this candidate explicitly replaces.

        Returns the retired memory id, or ``None`` when nothing was superseded.
        The lookup is scope-filtered, so a candidate cannot retire another
        tenant's or user's memory by naming its id.
        """
        superseded_id = self._normalize_text(normalized.get("supersedes"))
        if not superseded_id:
            return None
        collection, doc = self._find_memory_document(superseded_id)
        if collection is None or not doc:
            return None
        collection.update_one(
            scope_filter({"id": superseded_id}),
            {
                "$set": {
                    "status": MEMORY_STATUS_SUPERSEDED,
                    "superseded_by": normalized["id"],
                    "updated_at": self._now_fn(),
                }
            },
        )
        if self._index_client.is_enabled():
            try:
                self._index_client.delete_memory(superseded_id)
            except MemoryVectorIndexError as exc:
                self._record_failure("supersede_memory", FAILURE_CLASS_VECTOR_INDEX)
                collection.update_one(
                    scope_filter({"id": superseded_id}),
                    {"$set": {"retrieval.embedding_status": EMBEDDING_STATUS_DELETE_PENDING}},
                )
                self.logger.log(
                    "memory_service:_apply_supersession",
                    "Superseded memory still has a vector point; reconciliation required",
                    {"memory_id": superseded_id, "error": str(exc)},
                    "W",
                )
        self._record_operation("supersede_memory")
        return superseded_id

    def _merge_episodic_memory(self, normalized: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str]:
        """Insert or merge episodic memories."""
        collection = self._episodic_collection()
        existing = self._find_similar_episodic_memory(normalized)
        if existing:
            merged = copy.deepcopy(existing)
            incoming_text = normalized["content"]["text"]
            current_text = existing.get("content", {}).get("text", "")
            merged["content"] = {
                "text": incoming_text if len(incoming_text) > len(current_text) else current_text,
                "summary": normalized["content"]["summary"]
                if len(normalized["content"]["summary"]) >= len(existing.get("content", {}).get("summary", ""))
                else existing.get("content", {}).get("summary", normalized["content"]["summary"]),
            }
            merged["confidence"] = max(existing.get("confidence", 0.0), normalized["confidence"])
            merged["importance"] = max(existing.get("importance", 0.0), normalized["importance"])
            merged["stability"] = max(existing.get("stability", 0.0), normalized["stability"])
            merged["tags"] = self._as_string_list(existing.get("tags", []) + normalized["tags"])
            merged["source"] = normalized["source"] or existing.get("source")
            merged["updated_at"] = self._now_fn()
            merged["event_at"] = normalized.get("event_at") or existing.get("event_at")
            merged["expires_at"] = normalized.get("expires_at") or existing.get("expires_at")
            merged["provenance"] = self._merge_provenance(existing.get("provenance"), normalized.get("provenance"))
            merged["retrieval"] = self._merged_retrieval_state(existing, normalized)
            merged["status"] = MEMORY_STATUS_ACTIVE
            merged["revision"] = self._coerce_int(existing.get("revision"), 1) + 1
            merged["content_hash"] = self._content_hash(
                merged["owner_id"],
                merged["owner_type"],
                merged["memory_class"],
                merged["content"]["text"],
            )
            self._persist_memory(collection, merged, is_update=True)
            return merged, "merged", "merged with similar episodic memory"

        self._persist_memory(collection, normalized, is_update=False)
        return normalized, "accepted", "stored episodic memory"

    def _upsert_semantic_preference(self, normalized: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str]:
        """Insert or upsert semantic preference memories."""
        collection = self._semantic_collection()
        existing = collection.find_one(
            scope_filter({
                "owner_id": normalized["owner_id"],
                "owner_type": normalized["owner_type"],
                "preference_key": normalized["preference_key"],
                "archived_at": None,
            }),
            {"_id": 0},
        )
        if existing:
            merged = copy.deepcopy(existing)
            explicit_signal = bool(normalized["provenance"].get("explicit_user_signal"))
            merged["value"] = copy.deepcopy(normalized["value"])
            merged["value_type"] = normalized["value_type"]
            merged["content"] = copy.deepcopy(normalized["content"]) if explicit_signal else {
                "text": normalized["content"]["text"] or existing.get("content", {}).get("text", ""),
                "summary": normalized["content"]["summary"] or existing.get("content", {}).get("summary", ""),
            }
            merged["strength"] = min(1.0, max(existing.get("strength", 0.0), normalized["strength"]) + 0.05)
            merged["confidence"] = max(existing.get("confidence", 0.0), normalized["confidence"])
            merged["importance"] = max(existing.get("importance", 0.0), normalized["importance"])
            merged["evidence_count"] = max(1, existing.get("evidence_count", 0)) + max(
                1, normalized.get("evidence_count", 1)
            )
            merged["tags"] = self._as_string_list(existing.get("tags", []) + normalized["tags"])
            merged["updated_at"] = self._now_fn()
            merged["source"] = normalized["source"] or existing.get("source")
            merged["provenance"] = self._merge_provenance(existing.get("provenance"), normalized.get("provenance"))
            merged["retrieval"] = self._merged_retrieval_state(existing, normalized)
            # A preference key holds exactly one authoritative value, so a new
            # value supersedes the old one in place rather than creating a
            # second active memory that contradicts it.
            merged["status"] = MEMORY_STATUS_ACTIVE
            merged["revision"] = self._coerce_int(existing.get("revision"), 1) + 1
            merged["content_hash"] = self._content_hash(
                merged["owner_id"],
                merged["owner_type"],
                merged["memory_class"],
                merged["content"]["text"],
            )
            self._persist_memory(collection, merged, is_update=True)
            return merged, "merged", "upserted semantic preference"

        self._persist_memory(collection, normalized, is_update=False)
        return normalized, "accepted", "stored semantic preference"

    def write_memory(
        self,
        candidate: Optional[Dict[str, Any]],
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validate, persist, and index a memory candidate."""
        self._ensure_indexes()
        started = time.monotonic()
        self._record_operation("write_memory")
        request_context = copy.deepcopy(request_context or {})
        candidate_snapshot = copy.deepcopy(candidate or {})

        request_id = request_context.get("request_id")
        if request_id:
            existing_log = self._write_log_collection().find_one(scope_filter({"request_id": request_id}), {"_id": 0})
            if existing_log:
                return self._result_from_log(existing_log)

        try:
            normalized = self._normalize_candidate(candidate_snapshot, request_context)
            request_context.setdefault("owner_id", normalized["owner_id"])
            request_context.setdefault("owner_type", normalized["owner_type"])

            accepted, checks, reason = self._evaluate_write_policy(normalized)
            if not accepted:
                self._record_failure("write_memory", FAILURE_CLASS_VALIDATION)
                self._log_outcome(
                    request_context,
                    candidate_snapshot,
                    normalized,
                    "rejected",
                    None,
                    normalized.get("memory_class"),
                    reason,
                    checks,
                )
                self._record_duration("write_memory", started)
                return {
                    "status": "rejected",
                    "memory_id": None,
                    "memory_class": normalized.get("memory_class"),
                    "reason": reason,
                    "qdrant_indexed": None,
                    "embedding_status": None,
                    "reconciliation_required": False,
                }

            # Exact duplicates never become a second active memory: the
            # existing record is returned untouched so the owner keeps exactly
            # one authoritative copy of a fact it already stores.
            duplicate = self._find_active_duplicate(normalized)
            if duplicate is not None:
                self._log_outcome(
                    request_context,
                    candidate_snapshot,
                    normalized,
                    "duplicate",
                    duplicate["id"],
                    duplicate["memory_class"],
                    "identical active memory already stored",
                    checks,
                )
                self._record_duration("write_memory", started)
                return {
                    "status": "duplicate",
                    "memory_id": duplicate["id"],
                    "memory_class": duplicate["memory_class"],
                    "reason": "identical active memory already stored",
                    "qdrant_indexed": None,
                    "embedding_status": duplicate.get("retrieval", {}).get("embedding_status"),
                    "reconciliation_required": False,
                }

            superseded_id = self._apply_supersession(normalized)

            if normalized["memory_class"] == "semantic_preference":
                stored_doc, status, reason = self._upsert_semantic_preference(normalized)
            else:
                stored_doc, status, reason = self._merge_episodic_memory(normalized)

            qdrant_indexed, qdrant_error = self._sync_vector_index(stored_doc)
            embedding_status = stored_doc["retrieval"]["embedding_status"]

            self._log_outcome(
                request_context,
                candidate_snapshot,
                normalized,
                status,
                stored_doc["id"],
                stored_doc["memory_class"],
                reason,
                checks,
                qdrant_indexed=qdrant_indexed,
                qdrant_error=qdrant_error,
            )
            self._record_duration("write_memory", started)
            return {
                "status": status,
                "memory_id": stored_doc["id"],
                "memory_class": stored_doc["memory_class"],
                "reason": reason,
                "qdrant_indexed": qdrant_indexed,
                "embedding_status": embedding_status,
                "reconciliation_required": embedding_status in RECONCILIATION_STATUSES,
                "superseded_memory_id": superseded_id,
            }
        except Exception as exc:
            self._record_failure("write_memory", FAILURE_CLASS_DATABASE)
            self._record_duration("write_memory", started)
            self._log_outcome(
                request_context,
                candidate_snapshot,
                None,
                "failed",
                None,
                None,
                str(exc),
                None,
            )
            self.logger.log(
                "memory_service:write_memory",
                "Failed to write memory",
                {"error": str(exc), "request_context": request_context},
                "E",
            )
            raise DatabaseError(f"Failed to write memory: {exc}")

    def _keyword_overlap(self, query_tokens: List[str], memory_tokens: List[str]) -> float:
        """Calculate token overlap ratio."""
        if not query_tokens or not memory_tokens:
            return 0.0
        overlap = len(set(query_tokens) & set(memory_tokens))
        return overlap / max(len(set(query_tokens)), 1)

    def _episodic_recency_score(self, event_at: Any) -> float:
        """Decay episodic score as events become older."""
        event_time = _parse_datetime(event_at)
        if not event_time:
            return 0.5
        days_old = max((datetime.now(timezone.utc) - event_time).days, 0)
        return 1.0 / (1.0 + (days_old / 30.0))

    def _score_document(
        self,
        doc: Dict[str, Any],
        query_tokens: List[str],
        qdrant_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        """Compute ranking details for a memory document."""
        memory_tokens = doc.get("retrieval", {}).get("keywords", []) or self._tokenize(doc.get("content", {}).get("text", ""))
        keyword_overlap = self._keyword_overlap(query_tokens, memory_tokens)
        lexical_similarity = self._text_similarity(query_tokens, memory_tokens)
        semantic_relevance = qdrant_scores.get(doc["id"], lexical_similarity)
        importance = self._coerce_float(doc.get("importance"), 0.0)

        if doc["memory_class"] == "episodic":
            class_signal = self._episodic_recency_score(doc.get("event_at"))
        else:
            class_signal = self._coerce_float(doc.get("strength"), self._coerce_float(doc.get("confidence"), 0.5))

        score = (
            (0.40 * semantic_relevance)
            + (0.25 * keyword_overlap)
            + (0.15 * importance)
            + (0.20 * class_signal)
        )
        if doc["memory_class"] == "semantic_preference" and doc.get("provenance", {}).get("explicit_user_signal"):
            score += 0.05

        return {
            "score": round(score, 6),
            "semantic_relevance": round(semantic_relevance, 6),
            "keyword_overlap": round(keyword_overlap, 6),
            "importance": round(importance, 6),
            "class_signal": round(class_signal, 6),
        }

    def _diversify_ranked_documents(
        self,
        ranked_documents: List[Tuple[Dict[str, Any], Dict[str, Any]]],
        limit: int,
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Keep semantic preferences from crowding out episodic results."""
        episodic = [item for item in ranked_documents if item[0]["memory_class"] == "episodic"]
        semantic = [item for item in ranked_documents if item[0]["memory_class"] == "semantic_preference"]
        had_episodic_candidates = bool(episodic)
        max_semantic = max(1, math.ceil(limit / 2))

        results: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        semantic_count = 0
        while len(results) < limit and (episodic or semantic):
            appended = False
            if episodic:
                results.append(episodic.pop(0))
                appended = True
                if len(results) >= limit:
                    break
            if semantic and (semantic_count < max_semantic or not had_episodic_candidates):
                results.append(semantic.pop(0))
                semantic_count += 1
                appended = True

            # Stop once the class-balance rule cannot add any more results.
            if not appended:
                break

        if len(results) < limit:
            leftovers = episodic if had_episodic_candidates else semantic
            results.extend(leftovers[: max(0, limit - len(results))])

        return results[:limit]

    def _update_last_accessed(self, memory_ids: List[str]) -> None:
        """Touch last_accessed_at for returned memories."""
        timestamp = self._now_fn()
        for memory_id in memory_ids:
            collection, _ = self._find_memory_document(memory_id)
            if collection is None:
                continue
            collection.update_one(
                scope_filter({"id": memory_id}),
                {"$set": {"last_accessed_at": timestamp}},
            )

    def _semantic_candidates(
        self,
        query_text: str,
        owner_id: str,
        owner_type: str,
        limit: int,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float], str, Optional[str]]:
        """Run the semantic leg of retrieval.

        Returns the hits, their scores, the mode actually used, and — when the
        semantic path could not run — why. Callers report that reason instead
        of presenting keyword-only results as if they were semantic ones.
        """
        if not query_text:
            return [], {}, "lexical", "no query text supplied"
        if not self._index_client.is_enabled():
            return [], {}, "lexical", "vector index disabled"

        try:
            query_vector = self._embedding_client.embed_query(query_text)
        except MemoryEmbeddingError as exc:
            self._record_failure("get_relevant_memories", FAILURE_CLASS_EMBEDDING)
            self.logger.log(
                "memory_service:get_relevant_memories",
                "Query embedding failed; retrieval degraded to keyword ranking",
                {"error": str(exc)},
                "E",
            )
            return [], {}, "lexical", f"embedding unavailable: {exc}"

        try:
            hits = self._index_client.search(
                query_vector,
                owner_id,
                owner_type,
                limit=max(limit * 2, limit),
                statuses=sorted(RETRIEVABLE_STATUSES),
            )
        except MemoryVectorIndexError as exc:
            self._record_failure("get_relevant_memories", FAILURE_CLASS_VECTOR_INDEX)
            self.logger.log(
                "memory_service:get_relevant_memories",
                "Vector search failed; retrieval degraded to keyword ranking",
                {"error": str(exc)},
                "E",
            )
            return [], {}, "lexical", f"vector search unavailable: {exc}"

        scores = {
            hit["memory_id"]: float(hit.get("score", 0.0))
            for hit in hits
            if hit.get("memory_id")
        }
        return hits, scores, "semantic", None

    def get_relevant_memories(self, query_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Retrieve and rank relevant episodic and semantic preference memories."""
        self._ensure_indexes()
        started = time.monotonic()
        self._record_operation("get_relevant_memories")
        query_context = copy.deepcopy(query_context or {})

        identity = current_identity()
        owner_id = self._normalize_text(identity.user_id if identity is not None else query_context.get("owner_id"))
        owner_type = self._normalize_text("user" if identity is not None else query_context.get("owner_type") or "user").lower()
        if not owner_id:
            raise DatabaseError("owner_id is required for memory retrieval")
        if owner_type not in ALLOWED_OWNER_TYPES:
            raise DatabaseError("owner_type is invalid for memory retrieval")

        memory_classes = query_context.get("memory_classes") or list(ALLOWED_MEMORY_CLASSES)
        memory_classes = [memory_class for memory_class in memory_classes if memory_class in ALLOWED_MEMORY_CLASSES]
        if not memory_classes:
            memory_classes = list(ALLOWED_MEMORY_CLASSES)

        query_text = self._normalize_text(
            query_context.get("text")
            or query_context.get("query")
            or query_context.get("query_text")
            or ""
        )
        query_tokens = self._as_string_list(query_context.get("keywords")) or self._tokenize(query_text)
        limit = max(1, self._coerce_int(query_context.get("limit"), settings.memory_retrieval_default_limit))
        include_debug = bool(query_context.get("include_debug"))

        mongo_candidates = self._active_memory_documents(
            owner_id=owner_id,
            owner_type=owner_type,
            memory_classes=memory_classes,
            include_archived=False,
        )

        qdrant_hits, qdrant_scores, retrieval_mode, degraded_reason = self._semantic_candidates(
            query_text,
            owner_id,
            owner_type,
            limit,
        )

        ranked: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        for doc in mongo_candidates:
            ranking = self._score_document(doc, query_tokens, qdrant_scores)
            if ranking["score"] <= 0 and query_tokens:
                continue
            ranked.append((doc, ranking))

        if not ranked and not query_tokens:
            for doc in mongo_candidates:
                ranked.append((doc, self._score_document(doc, [], qdrant_scores)))

        # Ties break on updated_at and then on id, so an identical corpus and
        # query always produce the same ordering — the property the retrieval
        # measurement depends on.
        ranked.sort(
            key=lambda item: (
                item[1]["score"],
                item[0].get("updated_at") or "",
                item[0]["id"],
            ),
            reverse=True,
        )
        diversified = self._diversify_ranked_documents(ranked, limit)
        self._update_last_accessed([doc["id"] for doc, _ in diversified])

        memories: List[Dict[str, Any]] = []
        for rank, (doc, ranking) in enumerate(diversified, start=1):
            ranking_payload = dict(ranking)
            ranking_payload["rank"] = rank
            memories.append(self._normalize_output_memory(doc, ranking_payload))

        METRICS.memory_retrieval_results.labels(
            service=settings.service_name,
            retrieval_mode=retrieval_mode,
        ).observe(len(memories))
        self._record_duration("get_relevant_memories", started)

        response: Dict[str, Any] = {
            "status": "success",
            "memories": memories,
            "retrieval_mode": retrieval_mode,
            "degraded": retrieval_mode != "semantic",
            "degraded_reason": degraded_reason,
            "provenance": {
                **self.index_provenance(),
                "scope": {
                    "tenant_scoped": identity is not None,
                    "user_scoped": identity is not None,
                    "owner_id": owner_id,
                    "owner_type": owner_type,
                    "memory_classes": sorted(memory_classes),
                    "statuses": sorted(RETRIEVABLE_STATUSES),
                },
            },
        }
        if include_debug:
            response["debug"] = {
                "mongo_candidate_count": len(mongo_candidates),
                "qdrant_candidate_count": len(qdrant_hits),
                "qdrant_memory_ids": [hit.get("memory_id") for hit in qdrant_hits if hit.get("memory_id")],
            }
        return response

    def list_memory_for_debug(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """List stored memories for internal debugging and inspection."""
        self._ensure_indexes()
        filters = copy.deepcopy(filters or {})
        identity = current_identity()
        owner_id = self._normalize_text(identity.user_id if identity is not None else filters.get("owner_id"))
        owner_type = "user" if identity is not None else self._normalize_text(filters.get("owner_type")).lower() if filters.get("owner_type") else None
        memory_class = self._normalize_text(filters.get("memory_class")).lower() or None
        include_archived = bool(filters.get("include_archived"))
        tag = self._normalize_text(filters.get("tag")).lower() or None
        preference_key = self._normalize_text(filters.get("preference_key")).lower() or None
        include_write_log = bool(filters.get("include_write_log"))
        limit = max(1, self._coerce_int(filters.get("limit"), 50))

        documents = self._active_memory_documents(
            owner_id=owner_id or None,
            owner_type=owner_type,
            memory_classes=[memory_class] if memory_class else None,
            include_archived=include_archived,
        )
        filtered: List[Dict[str, Any]] = []
        for doc in documents:
            if tag and tag not in self._as_string_list(doc.get("tags", [])):
                continue
            if preference_key and doc.get("preference_key") != preference_key:
                continue
            filtered.append(doc)

        filtered.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        response: Dict[str, Any] = {
            "status": "success",
            "memories": [self._normalize_output_memory(doc) for doc in filtered[:limit]],
        }
        if include_write_log:
            logs = list(self._write_log_collection().find(scope_filter(), {"_id": 0}))
            if owner_id:
                logs = [log for log in logs if log.get("owner_id") == owner_id]
            if owner_type:
                logs = [log for log in logs if log.get("owner_type") == owner_type]
            logs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
            response["write_log"] = logs[:limit]
        return response

    def get_all_memories(self) -> List[Dict[str, Any]]:
        """Return all memories in a legacy-friendly flattened format."""
        self._ensure_indexes()
        documents = self._all_memory_documents()
        documents.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return [self._to_legacy_memory(doc) for doc in documents]

    def get_memory(self, memory_id: str) -> Dict[str, Any]:
        """Get a memory by id in a legacy-friendly flattened format."""
        self._ensure_indexes()
        _, doc = self._find_memory_document(memory_id)
        if not doc:
            raise ValueError(f"Memory {memory_id} not found")
        return self._to_legacy_memory(doc)

    def create_memory(
        self,
        content: str,
        category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Legacy wrapper for creating memories."""
        metadata = metadata or {}
        owner_id = metadata.get("owner_id") or metadata.get("chat_id") or metadata.get("conversation_id") or "legacy-owner"
        owner_type = metadata.get("owner_type") or ("conversation" if metadata.get("chat_id") or metadata.get("conversation_id") else "user")
        memory_class = "semantic_preference" if "preference" in self._normalize_text(category).lower() else None
        candidate = {
            "memory_class": memory_class,
            "content": {
                "text": content,
                "summary": metadata.get("summary"),
            },
            "source": metadata.get("source", "legacy_create_memory"),
            "tags": metadata.get("tags", []),
            "provenance": metadata.get("provenance") or {
                "chat_id": metadata.get("chat_id"),
                "explicit_user_signal": metadata.get("explicit_user_signal", False),
            },
            "event_at": metadata.get("event_at"),
            "preference_key": metadata.get("preference_key"),
            "value": metadata.get("value"),
            "evidence_count": metadata.get("evidence_count"),
        }
        result = self.write_memory(
            candidate,
            {"owner_id": owner_id, "owner_type": owner_type, "source": "legacy_create_memory"},
        )
        if result["status"] not in {"accepted", "merged"} or not result["memory_id"]:
            raise DatabaseError(result["reason"])
        return self.get_memory(result["memory_id"])

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Legacy wrapper for updating a memory by id."""
        del category
        metadata = metadata or {}
        collection, doc = self._find_memory_document(memory_id)
        if not collection or not doc:
            raise ValueError(f"Memory {memory_id} not found")

        updated = copy.deepcopy(doc)
        content_changed = False
        if content is not None:
            updated["content"] = {
                "text": self._normalize_text(content),
                "summary": self._build_summary(self._normalize_text(content)),
            }
            updated["retrieval"]["keywords"] = self._as_string_list(
                updated["tags"] + self._tokenize(updated["content"]["text"])[:12]
            )
            updated["content_hash"] = self._content_hash(
                updated["owner_id"],
                updated["owner_type"],
                updated["memory_class"],
                updated["content"]["text"],
            )
            content_changed = True
        if metadata:
            if "tags" in metadata:
                updated["tags"] = self._as_string_list(metadata["tags"])
            if "provenance" in metadata and isinstance(metadata["provenance"], dict):
                updated["provenance"] = self._merge_provenance(updated.get("provenance"), metadata["provenance"])
            if updated["memory_class"] == "semantic_preference":
                if "value" in metadata:
                    updated["value"] = metadata["value"]
                    updated["value_type"] = self._infer_value_type(metadata["value"])
                if "strength" in metadata:
                    updated["strength"] = self._coerce_float(metadata["strength"], updated.get("strength", 0.7))
                if "evidence_count" in metadata:
                    updated["evidence_count"] = self._coerce_int(metadata["evidence_count"], updated.get("evidence_count", 1))
            else:
                if "event_at" in metadata:
                    updated["event_at"] = metadata["event_at"]
                if "expires_at" in metadata:
                    updated["expires_at"] = metadata["expires_at"]
                if "stability" in metadata:
                    updated["stability"] = self._coerce_float(metadata["stability"], updated.get("stability", 0.6))
        # An update replaces the fact in place, so the record stays the single
        # authoritative memory and only its revision moves forward.
        updated["updated_at"] = self._now_fn()
        updated["revision"] = self._coerce_int(updated.get("revision"), 1) + 1
        updated["status"] = MEMORY_STATUS_ACTIVE
        if content_changed and self._index_client.is_enabled():
            updated["retrieval"]["embedding_status"] = EMBEDDING_STATUS_PENDING
        collection.update_one(scope_filter({"id": memory_id}), {"$set": updated})
        self._record_operation("update_memory")
        if self._index_client.is_enabled():
            self._sync_vector_index(updated)
        return self.get_memory(memory_id)

    def delete_memory(self, memory_id: str) -> Dict[str, Any]:
        """Delete a memory from both canonical persistence and the index.

        Deletion is only complete when both sides are gone. If the vector point
        cannot be removed, the canonical document is kept as a `deleted`
        tombstone — invisible to every read path but still carrying the id the
        index needs — and the caller is told the delete is partial rather than
        being handed a success it did not get.
        """
        started = time.monotonic()
        self._record_operation("delete_memory")
        collection, doc = self._find_memory_document(memory_id)
        if not collection or not doc:
            raise ValueError(f"Memory {memory_id} not found")

        if self._index_client.is_enabled():
            try:
                self._index_client.delete_memory(memory_id)
            except MemoryVectorIndexError as exc:
                self._record_failure("delete_memory", FAILURE_CLASS_VECTOR_INDEX)
                collection.update_one(
                    scope_filter({"id": memory_id}),
                    {
                        "$set": {
                            "status": MEMORY_STATUS_DELETED,
                            "deleted_at": self._now_fn(),
                            "updated_at": self._now_fn(),
                            "retrieval.embedding_status": EMBEDDING_STATUS_DELETE_PENDING,
                        }
                    },
                )
                self.logger.log(
                    "memory_service:delete_memory",
                    "Vector point survived a memory delete; reconciliation required",
                    {"memory_id": memory_id, "error": str(exc)},
                    "E",
                )
                self._record_duration("delete_memory", started)
                return {
                    "status": "partial",
                    "memory_id": memory_id,
                    "vector_deleted": False,
                    "reconciliation_required": True,
                    "reason": str(exc),
                }

        result = collection.delete_one(scope_filter({"id": memory_id}))
        if result.deleted_count == 0:
            raise ValueError(f"Memory {memory_id} not found")
        self._record_duration("delete_memory", started)
        return {
            "status": "deleted",
            "memory_id": memory_id,
            "vector_deleted": self._index_client.is_enabled(),
            "reconciliation_required": False,
            "reason": None,
        }

    def delete_memories_by_chat_id(self, chat_id: str) -> int:
        """Delete memories associated with a conversation owner or provenance.chat_id.

        Returns the number fully deleted; a memory left as a tombstone by a
        failed vector delete is not counted as deleted.
        """
        deleted = 0
        for doc in self._all_memory_documents():
            provenance = doc.get("provenance", {})
            if (doc.get("owner_type") == "conversation" and doc.get("owner_id") == chat_id) or provenance.get("chat_id") == chat_id:
                try:
                    if self.delete_memory(doc["id"])["status"] == "deleted":
                        deleted += 1
                except ValueError:
                    continue
        return deleted

    def get_user_insight(self) -> Optional[Dict[str, Any]]:
        """Return no durable user-insight record for the deprecated compatibility surface."""
        self.logger.log(
            "memory_service:get_user_insight",
            "user_insight is deprecated and not persisted in the canonical memory model",
            {},
        )
        return None

    def create_user_insight(self, insight: str) -> Dict[str, Any]:
        """Return an ephemeral compatibility payload without persisting canonical state."""
        self.logger.log(
            "memory_service:create_user_insight",
            "user_insight is deprecated and not persisted in the canonical memory model",
            {"length": len(insight or "")},
        )
        return {
            "id": str(uuid.uuid4()),
            "content": insight,
            "category": "user_insight",
            "metadata": {"deprecated": True},
            "created_at": self._now_fn(),
            "updated_at": self._now_fn(),
        }

    def update_user_insight(self, insight: str) -> Dict[str, Any]:
        """Return the same ephemeral compatibility payload as create_user_insight."""
        return self.create_user_insight(insight)
