"""Bounded reconciliation between canonical memory and the vector index.

MongoDB is authoritative and the vector index is derived, so the two can
disagree: an embedding call failed, a delete removed the row but not the
point, a process died between the two writes. MEMORY-V2-01 made every such
divergence explicit instead of silent; this module is what closes them.

Three properties shape the design:

* **Bounded.** One run repairs at most a configured number of memories and
  scans at most one page of index points. There is no global rebuild, because
  a repair path that can only run as a full sweep is a repair path nobody runs.
* **Idempotent.** Every action is safe to repeat. A run over already-consistent
  state performs no writes and reports no drift, so a retry after a crash is
  free rather than dangerous.
* **Tenant-safe.** Every read and write goes through the same scope filter the
  service uses, and the index scroll is filtered to the caller's tenant and
  user. Reconciliation never sees, let alone repairs, another tenant's data.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set

from app.core.config import settings
from app.services.memory_embedding_client import MemoryEmbeddingError
from app.services.memory_service import (
    EMBEDDING_STATUS_DELETE_PENDING,
    EMBEDDING_STATUS_DISABLED,
    EMBEDDING_STATUS_FAILED,
    EMBEDDING_STATUS_INDEXED,
    EMBEDDING_STATUS_PENDING,
    MEMORY_STATUS_DELETED,
    MEMORY_STATUS_SUPERSEDED,
    RECONCILIATION_STATUSES,
)
from app.services.memory_vector_index import MemoryVectorIndexError
from app.services.tenant_scope import current_identity, scope_filter
from shared.logging import ServiceLogger
from shared.metrics import METRICS

# Drift classes. Closed vocabulary: these are every way canonical memory and
# the index are known to be able to disagree, and each one is a metric label.
DRIFT_MISSING_VECTOR = "missing_vector"
DRIFT_STALE_VECTOR = "stale_vector"
DRIFT_TOMBSTONE_VECTOR = "tombstone_vector"
DRIFT_ORPHAN_VECTOR = "orphan_vector"
DRIFT_DUPLICATE_VECTOR = "duplicate_vector"

DRIFT_CLASSES = {
    DRIFT_MISSING_VECTOR,
    DRIFT_STALE_VECTOR,
    DRIFT_TOMBSTONE_VECTOR,
    DRIFT_ORPHAN_VECTOR,
    DRIFT_DUPLICATE_VECTOR,
}

OUTCOME_REPAIRED = "repaired"
OUTCOME_FAILED = "failed"
OUTCOME_SKIPPED = "skipped"


class MemoryReconciliationService:
    """Repair divergence between memory persistence and the vector index."""

    def __init__(self, memory_service: Any, logger: ServiceLogger) -> None:
        self.memory_service = memory_service
        self.logger = logger

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def _record(self, drift_class: str, outcome: str) -> None:
        METRICS.memory_reconciliation_total.labels(
            service=settings.service_name,
            drift_class=drift_class,
            outcome=outcome,
        ).inc()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconcile(
        self,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run one bounded reconciliation pass for the calling identity.

        Args:
            limit: How many canonical memories to repair and how many index
                points to scan in this pass. Defaults to the configured batch
                limit.
            cursor: Index scroll position from a previous run's
                ``next_cursor``, so a large collection is walked across several
                bounded passes instead of one unbounded sweep.

        Returns:
            A report naming every drift found, what was repaired, and what
            remains — never a bare success count, because an unrepaired
            divergence is exactly the thing a caller has to know about.
        """
        started = time.monotonic()
        service = self.memory_service
        index = service._index_client
        batch = max(1, int(limit or settings.memory_reconciliation_batch_limit))

        report: Dict[str, Any] = {
            "status": "success",
            "scanned": 0,
            "drift": {drift_class: 0 for drift_class in sorted(DRIFT_CLASSES)},
            "repaired": 0,
            "failed": 0,
            "unresolved": [],
            "next_cursor": None,
            "truncated": False,
            "index_enabled": index.is_enabled(),
        }

        if not index.is_enabled():
            # Nothing derived exists, so nothing can diverge. Reporting this as
            # a skip rather than a clean run keeps "no drift" from meaning two
            # different things.
            report["status"] = "skipped"
            report["reason"] = "vector index is disabled"
            METRICS.memory_reconciliation_duration.labels(service=settings.service_name).observe(
                time.monotonic() - started
            )
            return report

        documents = service._all_memory_documents(include_tombstones=True)
        report["scanned"] = len(documents)
        known_ids = {str(doc.get("id")) for doc in documents}
        # Which of the scanned rows are already owned by a durable deletion
        # identity, resolved in one bounded query rather than one per document.
        deleted_ids = service._deletion_tombstone_ids(known_ids)

        # The bound counts work done, not documents looked at. Slicing the
        # document list instead would make every pass revisit the same head of
        # the collection, so a run could never make progress past its own
        # limit however many times it was invoked.
        attempted = 0
        for doc in documents:
            if attempted >= batch:
                report["truncated"] = True
                break
            if self._reconcile_document(doc, report, deleted_ids):
                attempted += 1

        if settings.memory_reconciliation_scan_orphans:
            report["next_cursor"] = self._reconcile_index_points(known_ids, batch, cursor, report)

        report["unresolved"] = sorted(set(report["unresolved"]))
        if report["failed"]:
            report["status"] = "partial"
        METRICS.memory_reconciliation_duration.labels(service=settings.service_name).observe(
            time.monotonic() - started
        )
        self.logger.log(
            "memory_reconciliation:reconcile",
            "Memory index reconciliation pass completed",
            {
                "scanned": report["scanned"],
                "repaired": report["repaired"],
                "failed": report["failed"],
                "drift": report["drift"],
            },
        )
        return report

    # ------------------------------------------------------------------
    # Canonical-side drift
    # ------------------------------------------------------------------

    def _reconcile_document(
        self,
        doc: Dict[str, Any],
        report: Dict[str, Any],
        deleted_ids: Set[str],
    ) -> bool:
        """Repair one canonical memory whose index state is behind.

        Returns whether this document needed work, so the caller can bound a
        pass by repairs attempted rather than by documents inspected.
        """
        service = self.memory_service
        status = service._memory_status(doc)
        retrieval = doc.get("retrieval") or {}
        embedding_status = retrieval.get("embedding_status")

        # A crash can leave the durable deletion identity committed while the
        # canonical row is still unmarked and its point still indexed. The
        # deletion identity is authoritative, so reconciliation finishes the
        # delete and never re-embeds the row back into the index.
        if str(doc.get("id") or "") in deleted_ids:
            self._repair_tombstone(doc, report, deleted_ids)
            return True

        if status in {MEMORY_STATUS_DELETED, MEMORY_STATUS_SUPERSEDED} or doc.get("valid_to"):
            if embedding_status == EMBEDDING_STATUS_DELETE_PENDING or (
                status == MEMORY_STATUS_DELETED and embedding_status != EMBEDDING_STATUS_DISABLED
            ):
                self._repair_tombstone(doc, report, deleted_ids)
                return True
            return False

        if embedding_status in {EMBEDDING_STATUS_PENDING, EMBEDDING_STATUS_FAILED}:
            self._repair_missing_vector(doc, DRIFT_MISSING_VECTOR, report)
            return True

        indexed_revision = retrieval.get("indexed_revision")
        if indexed_revision is not None and indexed_revision != doc.get("revision", 1):
            self._repair_missing_vector(doc, DRIFT_STALE_VECTOR, report)
            return True
        return False

    def _repair_missing_vector(self, doc: Dict[str, Any], drift_class: str, report: Dict[str, Any]) -> None:
        """Re-embed and re-upsert a memory the index does not correctly hold."""
        report["drift"][drift_class] += 1
        service = self.memory_service
        try:
            vector = service._embedding_client.embed_memory(doc.get("content", {}).get("text", ""))
            point_id = service._index_client.upsert_memory(doc, vector)
        except (MemoryEmbeddingError, MemoryVectorIndexError) as exc:
            report["failed"] += 1
            report["unresolved"].append(str(doc.get("id")))
            self._record(drift_class, OUTCOME_FAILED)
            self.logger.log(
                "memory_reconciliation:_repair_missing_vector",
                "Memory vector could not be repaired; it stays marked for reconciliation",
                {"memory_id": doc.get("id"), "drift_class": drift_class, "error": str(exc)},
                "W",
            )
            return

        doc["retrieval"].update(
            {
                "embedding_status": EMBEDDING_STATUS_INDEXED,
                "qdrant_point_id": point_id,
                "embedding_model": service._embedding_client.model,
                "embedding_dimensions": service._embedding_client.dimensions,
                "vector_collection": service._index_client.collection_name,
                "vector_synced_at": service._now_fn(),
                "indexed_revision": doc.get("revision", 1),
            }
        )
        doc["updated_at"] = service._now_fn()
        service._persist_retrieval_state(doc)
        report["repaired"] += 1
        self._record(drift_class, OUTCOME_REPAIRED)

    def _repair_tombstone(
        self,
        doc: Dict[str, Any],
        report: Dict[str, Any],
        deleted_ids: Set[str],
    ) -> None:
        """Finish a delete or supersession the index did not confirm.

        A tombstone exists only to remember which point still has to go. Once
        the point is gone the row has no reason to survive, so a deleted memory
        is removed for real; a superseded one keeps its history and merely
        stops owing the index anything. The durable deletion identity is not
        touched either way, so a later pass still refuses to resurrect the fact.
        """
        report["drift"][DRIFT_TOMBSTONE_VECTOR] += 1
        service = self.memory_service
        memory_id = str(doc.get("id"))
        try:
            service._index_client.delete_memory(memory_id)
        except MemoryVectorIndexError as exc:
            report["failed"] += 1
            report["unresolved"].append(memory_id)
            self._record(DRIFT_TOMBSTONE_VECTOR, OUTCOME_FAILED)
            self.logger.log(
                "memory_reconciliation:_repair_tombstone",
                "Vector point still survives a deleted memory",
                {"memory_id": memory_id, "error": str(exc)},
                "W",
            )
            return

        collection = service._collection_for(doc["memory_class"])
        if service._memory_status(doc) == MEMORY_STATUS_DELETED or memory_id in deleted_ids:
            collection.delete_one(scope_filter({"id": memory_id}))
        else:
            collection.update_one(
                scope_filter({"id": memory_id}),
                {"$set": {"retrieval.embedding_status": EMBEDDING_STATUS_DISABLED, "retrieval.qdrant_point_id": None}},
            )
        report["repaired"] += 1
        self._record(DRIFT_TOMBSTONE_VECTOR, OUTCOME_REPAIRED)

    # ------------------------------------------------------------------
    # Index-side drift
    # ------------------------------------------------------------------

    def _reconcile_index_points(
        self,
        known_ids: set,
        batch: int,
        cursor: Optional[str],
        report: Dict[str, Any],
    ) -> Optional[str]:
        """Remove index points no canonical memory owns any more.

        Two shapes of garbage live here: a point whose memory is gone entirely,
        and several points claiming the same memory — which can only happen
        when a point predates the deterministic point id, since the current
        scheme makes a repeat upsert overwrite rather than duplicate.
        """
        service = self.memory_service
        index = service._index_client
        identity = current_identity()
        try:
            points, next_cursor = index.scroll_points(batch, cursor)
        except MemoryVectorIndexError as exc:
            report["failed"] += 1
            self._record(DRIFT_ORPHAN_VECTOR, OUTCOME_FAILED)
            self.logger.log(
                "memory_reconciliation:_reconcile_index_points",
                "Could not scan index points for orphans",
                {"error": str(exc)},
                "W",
            )
            return None

        seen_memory_ids: Dict[str, str] = {}
        for point in points:
            payload = point.get("payload") or {}
            memory_id = str(payload.get("memory_id") or "")
            point_id = str(point.get("point_id") or "")

            if memory_id and memory_id not in known_ids:
                self._delete_point(DRIFT_ORPHAN_VECTOR, point_id, memory_id, report)
                continue

            canonical_point_id = (
                index.point_id(identity.tenant_id, identity.user_id, memory_id)
                if identity is not None and memory_id
                else None
            )
            if memory_id in seen_memory_ids or (
                canonical_point_id is not None and point_id and point_id != canonical_point_id
            ):
                self._delete_point(DRIFT_DUPLICATE_VECTOR, point_id, memory_id, report)
                continue
            if memory_id:
                seen_memory_ids[memory_id] = point_id

        return None if next_cursor is None else str(next_cursor)

    def _delete_point(
        self,
        drift_class: str,
        point_id: str,
        memory_id: str,
        report: Dict[str, Any],
    ) -> None:
        """Delete one stray index point, counting the outcome either way."""
        report["drift"][drift_class] += 1
        if not point_id:
            self._record(drift_class, OUTCOME_SKIPPED)
            return
        try:
            self.memory_service._index_client.delete_point(point_id)
        except MemoryVectorIndexError as exc:
            report["failed"] += 1
            report["unresolved"].append(memory_id or point_id)
            self._record(drift_class, OUTCOME_FAILED)
            self.logger.log(
                "memory_reconciliation:_delete_point",
                "Stray index point could not be removed",
                {"memory_id": memory_id, "drift_class": drift_class, "error": str(exc)},
                "W",
            )
            return
        report["repaired"] += 1
        self._record(drift_class, OUTCOME_REPAIRED)

    def drift_report(self) -> Dict[str, Any]:
        """Return what currently owes reconciliation, without repairing it.

        Deliberately read-only: an operator asking "is memory consistent?"
        should not have to trigger writes to find out.
        """
        service = self.memory_service
        owing: List[Dict[str, Any]] = []
        for doc in service._all_memory_documents(include_tombstones=True):
            embedding_status = (doc.get("retrieval") or {}).get("embedding_status")
            if embedding_status in RECONCILIATION_STATUSES:
                owing.append(
                    {
                        "memory_id": doc.get("id"),
                        "memory_class": doc.get("memory_class"),
                        "status": service._memory_status(doc),
                        "embedding_status": embedding_status,
                        "revision": doc.get("revision", 1),
                    }
                )
        return {
            "status": "success",
            "index_enabled": service._index_client.is_enabled(),
            "pending_count": len(owing),
            "pending": owing,
        }
