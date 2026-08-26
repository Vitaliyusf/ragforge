"""Golden-set datasets and eval runs, tenant-scoped in MongoDB.

Two collections, both admin-only and both scoped to exactly one tenant:

- ``eval_datasets`` — the golden set: a name and a list of canonical items.
  Items may carry resolved chunk/file ids or unresolved authoring filenames;
  the latter are preserved for a later resolution step and cannot be run yet.
- ``eval_runs`` — one execution of one dataset, carrying the config it ran
  under, its aggregate results, and a per-item row for drill-down.

Security invariants, identical in spirit to :mod:`app.services.metrics_query`:

- Every public method calls :func:`_require_admin` first.
- The tenant boundary is part of the query handed to MongoDB — the first
  ``$match`` of every pipeline — never a filter applied to rows in Python.
- An explicit ``tenant_id`` argument must equal the caller's own.

**Why ``config_snapshot`` is honest about what it cannot see.** Two runs are
only comparable if they ran under the same retrieval configuration, so the
snapshot is taken from live config at run start rather than from user input.
But rag can observe only its own settings: the embedding service's reply
carries no model name, the vector_db search reply carries no collection name,
and chunk strategy is a files-service concern rag never sees. Those three are
therefore read from the environment when it exposes them and otherwise listed
by name in ``unobserved``. That distinction matters: storing them as ``None``
would make two runs on *different* embedding models compare as identical, and
a config diff that reports "no change" wrongly is worse than one that says
"not captured".

**Why a dataset carries a version and a fingerprint.** A golden set whose
items can be replaced under a stable ``dataset_id`` makes two runs *look*
comparable when they scored different labels. Every dataset therefore also
carries ``dataset_version`` (starting at 1) and ``dataset_sha256``, a
deterministic hash of its canonical scoring content, and every run snapshots
both. See :func:`dataset_fingerprint` for exactly what the hash covers and
:meth:`EvalStore.update_dataset` for when the version moves.

The in-memory backend is a real implementation here, not the stub
``MetricsFactStore.aggregate`` uses. The eval harness has to be usable — and
testable — without a Mongo container, and every query this module issues is a
simple equality match with an optional sort and limit, which is small enough
to answer twice without writing a miniature MongoDB.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.core.config import RAGConfig
from app.services.golden_set_parser import (
    DEFAULT_MAX_INPUT_BYTES,
    GoldenSetValidationError,
    normalize_golden_set_items,
    parse_golden_set,
    validate_golden_set,
)
from shared.auth import AuthIdentity, identity_from_context

try:
    from pymongo import MongoClient
    from pymongo.collection import Collection
    _HAS_PYMONGO = True
except ImportError:  # pragma: no cover - exercised by the in-memory tests
    MongoClient = None
    Collection = Any
    _HAS_PYMONGO = False


DEFAULT_RUN_LIMIT = 20
MAX_RUN_LIMIT = 100

RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"

# Benchmark orchestration states. Defined here beside the run states for the
# same reason those are: they are persisted values, and the module that
# writes them owns their spelling.
#
# `partial` and `interrupted` exist because a multi-phase benchmark has two
# failure shapes an eval run does not. `partial` means some of it is real
# evidence and some is not — reporting that as `completed` would put an
# unmeasured phase on a chart, and reporting it as `failed` would throw away
# the phases that did run. `interrupted` means the orchestration was
# cancelled, typically by a service shutdown: the phases already closed are
# still valid, and the ones never reached were never attempted.
BENCHMARK_QUEUED = "queued"
BENCHMARK_RUNNING = "running"
BENCHMARK_COMPLETED = "completed"
BENCHMARK_PARTIAL = "partial"
BENCHMARK_FAILED = "failed"
BENCHMARK_INTERRUPTED = "interrupted"

# Settings rag cannot observe from its own process. Read from the environment
# where it happens to expose them; named in `unobserved` when it does not.
_ENV_SNAPSHOT_FIELDS = {
    "embedding_model": ("EMBEDDING_MODEL", "EMBEDDING_MODEL_NAME"),
    "vector_collection": ("VECTOR_DB_COLLECTION_NAME",),
    "chunk_strategy": ("CHUNK_STRATEGY",),
}


class EvalAccessDenied(PermissionError):
    """The caller is not an administrator of the tenant being addressed."""


class EvalValidationError(GoldenSetValidationError):
    """An uploaded dataset was rejected. The message says which item and why."""


class EvalNotFound(LookupError):
    """No dataset or run with that id exists in the caller's tenant."""


def _require_admin() -> AuthIdentity:
    """Return the calling identity, or refuse if it is not an admin.

    Deliberately a second copy of the check in ``metrics_query`` rather than
    an import of its private helper: the two modules raise different error
    types, and the RPC dispatch maps each to its own reply.

    Raises:
        EvalAccessDenied: If no identity is bound, or it is not an admin.
    """
    identity = identity_from_context(required=False)
    if identity is None or not identity.is_admin:
        raise EvalAccessDenied("Administrator role required for eval datasets")
    return identity


def _now() -> datetime:
    """Current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def build_config_snapshot(
    config: RAGConfig,
    *,
    mode: str = "retrieval",
    candidate_k: Optional[int] = None,
    pipeline_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Capture the configuration a run is about to execute under.

    Taken from live config at run start, never from the caller: a snapshot
    the user could supply would let two runs claim the same configuration
    while behaving differently.

    Args:
        config: Live rag configuration.
        mode: ``retrieval`` or ``end_to_end``. Recorded in the snapshot so the
            config-diff warning fires when a retrieval-only run is compared
            against a run that also generated and judged answers — they
            measure different systems and their numbers are not comparable.
        candidate_k: How many candidates the run's ranking was drawn from,
            supplied by the caller because it depends on the run's mode and
            not on config alone. It is recorded separately from
            ``top_k_documents``: two runs scored over different candidate
            depths are not comparable at the wider k values, and a snapshot
            showing only the production depth would hide that.
        pipeline_mode: Which conversation pipeline the run drove —
            ``regular``, ``extended``, or ``None`` when the run never went
            through one. It is a different axis from ``mode``: ``mode`` says
            how much of the stack was measured, ``pipeline_mode`` says which
            variant of the stack it was. Recorded as ``None`` rather than
            defaulted to ``regular`` for a retrieval-only run, because that
            run issues one pipeline-independent search and claiming a
            pipeline for it would invent a comparison axis it never varied.

    Returns:
        The observed settings, plus ``unobserved``: the names of the fields
        rag cannot see from its own process. A UI comparing two snapshots
        must treat an entry in ``unobserved`` as "unknown", not as a match.
    """
    snapshot: Dict[str, Any] = {
        "mode": mode,
        "pipeline_mode": pipeline_mode,
        "top_k_documents": config.top_k_documents,
        "candidate_k": candidate_k,
        "reranker_enabled": config.reranker_enabled,
        "reranker_top_k": config.reranker_top_k,
        "hybrid_search_enabled": config.hybrid_search_enabled,
        "hybrid_search_alpha": config.hybrid_search_alpha,
        "min_similarity_threshold": config.min_similarity_threshold,
    }
    unobserved: List[str] = []
    for field, env_names in _ENV_SNAPSHOT_FIELDS.items():
        value = next((os.getenv(name) for name in env_names if os.getenv(name)), None)
        snapshot[field] = value
        if value is None:
            unobserved.append(field)
    snapshot["unobserved"] = unobserved
    return snapshot


def normalize_items(
    raw_items: Any,
    *,
    max_items: int,
    max_query_length: int,
) -> List[Dict[str, Any]]:
    """Validate and normalize uploaded dataset items.

    Rejects rather than truncates, and says which item failed. A silently
    truncated or half-accepted dataset produces confident, wrong recall
    numbers, which is worse than an upload error.

    Args:
        raw_items: The uploaded items, expected to be a non-empty list.
        max_items: Cap on item count.
        max_query_length: Cap on the length of one query.

    Returns:
        Normalized items, each with an ``item_id``, ``query``,
        ``relevant_chunk_ids``, ``relevant_file_ids``, unresolved
        ``expected_file_names``, the optional ``expected_answer`` /
        ``expected_claims`` an ``end_to_end`` run reads, explicit unresolved
        expected facts, authoring metadata, and ``notes``. List fields are
        always lists and absent optional scalar fields are always ``None``.

    Raises:
        EvalValidationError: On any violation, naming the offending index.
    """
    try:
        return [
            dict(item)
            for item in normalize_golden_set_items(
                raw_items,
                max_items=max_items,
                max_query_length=max_query_length,
            )
        ]
    except GoldenSetValidationError as exc:
        raise EvalValidationError(str(exc)) from exc


# The first version every dataset carries, and the version assumed for a
# dataset written before versioning existed. See `_normalize_dataset`.
INITIAL_DATASET_VERSION = 1

# Fields of a normalized item that decide what a run scores. `item_id` and
# `notes` are deliberately absent — see `dataset_fingerprint`.
_SCORING_FIELDS = (
    "query",
    "relevant_chunk_ids",
    "relevant_file_ids",
    "expected_answer",
    "expected_claims",
)

_OPTIONAL_SCORING_FIELDS = ("expected_file_names", "answerable")


def canonical_items(items: Any) -> List[Dict[str, Any]]:
    """Reduce dataset items to the content a run's scores depend on.

    Two datasets whose canonical form is equal will score identically, and
    that is the only property the fingerprint claims. Concretely:

    - Only scoring fields survive. ``item_id`` is excluded because
      it is a uuid minted at upload when the file did not supply one: keeping
      it would give two uploads of the *same* labels two different hashes,
      which is precisely the false alarm the fingerprint exists to avoid.
      ``notes`` is excluded because it is human annotation no scorer reads.
      Unresolved filenames and ``answerable`` are included when supplied;
      absent values are omitted to keep pre-import fingerprints stable.
    - Id and claim lists are de-duplicated and sorted: they are matched as
      sets, so their order never reaches a score.
    - Items themselves are sorted by their canonical form, because the run
      scores every item independently and their order does not either.
    - Storage artefacts — Mongo ``_id``, timestamps, the dataset's name —
      never enter, so a hash is stable across a re-import or a rename.
    """
    canonical: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        entry: Dict[str, Any] = {}
        for field in _SCORING_FIELDS:
            value = item.get(field)
            if isinstance(value, list):
                entry[field] = sorted({str(element) for element in value})
            elif value is None or value == "":
                entry[field] = None
            else:
                entry[field] = str(value)
        for field in _OPTIONAL_SCORING_FIELDS:
            value = item.get(field)
            if isinstance(value, list):
                if value:
                    entry[field] = sorted({str(element) for element in value})
            elif value is not None:
                entry[field] = value
        canonical.append(entry)
    canonical.sort(key=_canonical_json)
    return canonical


def _canonical_json(value: Any) -> str:
    """Serialize to the one JSON form the hash is taken over."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def dataset_fingerprint(items: Any) -> str:
    """Hash the canonical scoring content of a dataset's items.

    Deterministic across processes and machines: the digest is taken over
    UTF-8 canonical JSON with sorted keys, so it depends on nothing but the
    values :func:`canonical_items` kept.

    Returns:
        A 64-character lowercase SHA-256 hex digest.
    """
    payload = _canonical_json(canonical_items(items)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class EvalStore:
    """Tenant-scoped persistence for eval datasets and runs."""

    def __init__(self, config: RAGConfig) -> None:
        self.config = config
        self._in_memory = (
            config.conversation_store_type.lower() == "in_memory" or not _HAS_PYMONGO
        )
        self._memory: Dict[str, List[Dict[str, Any]]] = {}
        self._client: Optional[MongoClient] = None
        self._db = None

    # ------------------------------------------------------------------
    # Datasets
    # ------------------------------------------------------------------

    def create_dataset(
        self,
        name: str,
        description: Optional[str],
        items: Any,
    ) -> Dict[str, Any]:
        """Validate and store one golden-set dataset.

        Raises:
            EvalAccessDenied: If the caller is not an admin.
            EvalValidationError: If the items fail validation.
        """
        identity = _require_admin()
        if not str(name or "").strip():
            raise EvalValidationError("A dataset needs a name")
        normalized = normalize_items(
            items,
            max_items=self.config.eval_max_dataset_items,
            max_query_length=self.config.eval_max_query_length,
        )
        timestamp = _now()
        document = {
            "dataset_id": str(uuid4()),
            "tenant_id": identity.tenant_id,
            "name": str(name).strip(),
            "description": str(description).strip() if description else None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "dataset_version": INITIAL_DATASET_VERSION,
            "dataset_sha256": dataset_fingerprint(normalized),
            "items": normalized,
        }
        self._insert(self.config.eval_datasets_collection, document)
        return _serialize(document)

    def import_dataset(
        self,
        name: str,
        description: Optional[str],
        content: Any,
        source_format: str,
    ) -> Dict[str, Any]:
        """Parse and store a JSON or JSONL Golden Set."""
        try:
            items = parse_golden_set(
                content,
                source_format,
                max_input_bytes=int(
                    getattr(self.config, "eval_max_dataset_bytes", DEFAULT_MAX_INPUT_BYTES)
                ),
                max_items=self.config.eval_max_dataset_items,
                max_query_length=self.config.eval_max_query_length,
            )
        except GoldenSetValidationError as exc:
            raise EvalValidationError(str(exc)) from exc
        return self.create_dataset(name, description, items)

    def validate_import(self, content: Any, source_format: str) -> Dict[str, Any]:
        """Return a complete validation report without storing anything."""
        _require_admin()
        return validate_golden_set(
            content,
            source_format,
            max_input_bytes=int(
                getattr(self.config, "eval_max_dataset_bytes", DEFAULT_MAX_INPUT_BYTES)
            ),
            max_items=self.config.eval_max_dataset_items,
            max_query_length=self.config.eval_max_query_length,
        )

    def parse_import(self, content: Any, source_format: str) -> List[Dict[str, Any]]:
        """Parse an import for preparation without storing it."""
        _require_admin()
        try:
            return [
                dict(item)
                for item in parse_golden_set(
                    content,
                    source_format,
                    max_input_bytes=int(
                        getattr(self.config, "eval_max_dataset_bytes", DEFAULT_MAX_INPUT_BYTES)
                    ),
                    max_items=self.config.eval_max_dataset_items,
                    max_query_length=self.config.eval_max_query_length,
                )
            ]
        except GoldenSetValidationError as exc:
            raise EvalValidationError(str(exc)) from exc

    def list_datasets(self) -> List[Dict[str, Any]]:
        """List the tenant's datasets, newest first, without their items.

        Items are omitted deliberately: the selector needs a count and a
        last-run time, and a 1000-item body per dataset would dwarf the rest
        of the panel's payload.
        """
        identity = _require_admin()
        datasets = self._query(
            self.config.eval_datasets_collection,
            {"tenant_id": identity.tenant_id},
            sort=("created_at", -1),
        )
        last_runs = self._last_run_times(identity)
        return [
            {
                "dataset_id": row.get("dataset_id"),
                "name": row.get("name"),
                "description": row.get("description"),
                "item_count": len(row.get("items") or []),
                "dataset_version": row.get("dataset_version"),
                "dataset_sha256": row.get("dataset_sha256"),
                "created_at": _iso(row.get("created_at")),
                "updated_at": _iso(row.get("updated_at")),
                "last_run_at": last_runs.get(row.get("dataset_id")),
            }
            for row in (_normalize_dataset(row) for row in datasets)
        ]

    def get_dataset(self, dataset_id: str) -> Dict[str, Any]:
        """Return one dataset with its items.

        Raises:
            EvalNotFound: If no such dataset exists in the caller's tenant.
        """
        identity = _require_admin()
        document = self._find_one(
            self.config.eval_datasets_collection,
            {"tenant_id": identity.tenant_id, "dataset_id": dataset_id},
        )
        if document is None:
            raise EvalNotFound(f"No eval dataset {dataset_id!r}")
        return _serialize(_normalize_dataset(document))

    def update_dataset(
        self,
        dataset_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        items: Any = None,
    ) -> Dict[str, Any]:
        """Rename a dataset or replace its items, versioning the content.

        Items are replaced wholesale rather than merged. A partial merge
        would need per-item identity the upload format does not guarantee,
        and silently keeping stale items is exactly the drift that makes a
        golden set untrustworthy.

        **When the version moves.** ``dataset_version`` increments if and
        only if ``dataset_sha256`` changes — that is, when the canonical
        scoring content of the items changes. The rule follows from what the
        pair is for: a run cites them to prove which labels produced its
        numbers, so the version must move exactly when a re-run could
        legitimately score differently.

        That decision means:

        - A **name or description edit does not increment.** It cannot change
          a single score, and bumping the version for it would make an
          honest regression look like a label change.
        - Re-uploading the **same** labels — reordered, re-keyed with fresh
          ``item_id``s, or with edited ``notes`` — does not increment either,
          for the same reason: :func:`canonical_items` shows nothing a scorer
          reads has moved.
        - Any change to a query, a relevant id, an expected answer or an
          expected claim increments, in **any** item.

        Raises:
            EvalNotFound: If no such dataset exists in the caller's tenant.
            EvalValidationError: If replacement items fail validation.
        """
        identity = _require_admin()
        scope = {"tenant_id": identity.tenant_id, "dataset_id": dataset_id}
        current = self._find_one(self.config.eval_datasets_collection, scope)
        if current is None:
            raise EvalNotFound(f"No eval dataset {dataset_id!r}")
        current = _normalize_dataset(current)

        changes: Dict[str, Any] = {"updated_at": _now()}
        if name is not None:
            if not str(name).strip():
                raise EvalValidationError("A dataset needs a name")
            changes["name"] = str(name).strip()
        if description is not None:
            changes["description"] = str(description).strip() or None
        if items is not None:
            normalized = normalize_items(
                items,
                max_items=self.config.eval_max_dataset_items,
                max_query_length=self.config.eval_max_query_length,
            )
            fingerprint = dataset_fingerprint(normalized)
            changes["items"] = normalized
            # Written on every item replacement, version bumped only on a
            # real content change: a re-upload that normalizes to the same
            # labels is the same label set, whatever the file looked like.
            changes["dataset_sha256"] = fingerprint
            if fingerprint != current.get("dataset_sha256"):
                changes["dataset_version"] = int(current["dataset_version"]) + 1
            else:
                changes["dataset_version"] = int(current["dataset_version"])
        else:
            # A metadata-only edit still persists whatever the normalization
            # inferred for a pre-versioning document, so the next read is not
            # inferring it again.
            changes["dataset_version"] = int(current["dataset_version"])
            changes["dataset_sha256"] = current["dataset_sha256"]

        updated = self._update_one(
            self.config.eval_datasets_collection, scope, changes
        )
        if not updated:
            raise EvalNotFound(f"No eval dataset {dataset_id!r}")
        return self.get_dataset(dataset_id)

    def delete_dataset(self, dataset_id: str) -> Dict[str, Any]:
        """Delete one dataset, leaving its runs in place.

        Past runs stay: they record what retrieval scored on a dataset that
        existed at the time, and deleting the history along with the labels
        would erase the regression evidence the panel exists to show.

        Raises:
            EvalNotFound: If no such dataset exists in the caller's tenant.
        """
        identity = _require_admin()
        deleted = self._delete_one(
            self.config.eval_datasets_collection,
            {"tenant_id": identity.tenant_id, "dataset_id": dataset_id},
        )
        if not deleted:
            raise EvalNotFound(f"No eval dataset {dataset_id!r}")
        return {"dataset_id": dataset_id, "deleted": True}

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def create_run(
        self,
        dataset_id: str,
        config_snapshot: Dict[str, Any],
        match_mode: str,
        mode: str = "retrieval",
        dataset_version: Optional[int] = None,
        dataset_sha256: Optional[str] = None,
        pipeline_mode: Optional[str] = None,
        benchmark_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Open a run document in ``running`` state and return it.

        Args:
            dataset_id: The dataset about to be executed.
            config_snapshot: From :func:`build_config_snapshot`.
            match_mode: ``chunk_id`` or ``file_id`` — recorded because
                file-level matching is coarser, and two runs using different
                modes are not comparable.
            mode: ``retrieval`` or ``end_to_end``. Stored at the top level as
                well as inside the snapshot so a run list can label each row
                without unpacking it.
            dataset_version: The dataset's version at run start, copied into
                the run and never revisited. A run reports what it scored,
                and reading the version back off a live dataset would make
                every past run re-describe itself after the next edit.
            dataset_sha256: The dataset's fingerprint at run start, snapshot
                for the same reason. ``dataset_id`` alone cannot prove two
                runs used the same labels; with these two it can.
            pipeline_mode: ``regular``, ``extended``, or ``None`` when the
                run drove no conversation pipeline. Stored beside ``mode``
                rather than folded into it: a run list has to be able to say
                "end-to-end, extended" without two enumerations meaning the
                same thing.
            benchmark_id: The benchmark orchestration this run is one phase
                of, or ``None`` for a run started on its own. A phase run is
                an ordinary eval run in every other respect — it is listed,
                fetched and scored identically — so the link is a field
                rather than a separate collection.
        """
        identity = _require_admin()
        document = {
            "run_id": str(uuid4()),
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "dataset_sha256": dataset_sha256,
            "tenant_id": identity.tenant_id,
            "started_at": _now(),
            "finished_at": None,
            "status": RUN_RUNNING,
            "match_mode": match_mode,
            "mode": mode,
            "pipeline_mode": pipeline_mode,
            "benchmark_id": benchmark_id,
            "config_snapshot": config_snapshot,
            # Filled in by `record_label_validation` before any item is
            # scored. It lives beside `results` rather than inside it so a
            # run that was refused for stale labels — and therefore has no
            # results at all — still says why.
            "label_validation": None,
            "results": {},
            "per_item": [],
            "error": None,
        }
        self._insert(self.config.eval_runs_collection, document)
        return _serialize(document)

    def record_label_validation(
        self,
        run_id: str,
        tenant_id: str,
        validation: Dict[str, Any],
    ) -> None:
        """Persist how the run's golden-set labels checked out.

        Written before scoring starts, so a run refused for stale labels
        carries the evidence for the refusal, and a run that proceeded
        carries proof that its labels were verified — or, when the check
        could not be made, that they were not.

        Takes ``tenant_id`` explicitly for the same reason
        :meth:`append_item_result` does: the caller is a background task with
        no request context left to read an identity from.
        """
        self._update_one(
            self.config.eval_runs_collection,
            {"tenant_id": tenant_id, "run_id": run_id},
            {"label_validation": validation},
        )

    def append_item_result(self, run_id: str, tenant_id: str, row: Dict[str, Any]) -> None:
        """Persist one finished item as it completes.

        Partial progress is written per item rather than once at the end so
        that a crashed run leaves evidence of how far it got.

        Takes ``tenant_id`` explicitly: this is called from a background task
        where the request context that carried the identity is long gone.
        """
        self._update_one(
            self.config.eval_runs_collection,
            {"tenant_id": tenant_id, "run_id": run_id},
            {},
            push=("per_item", row),
        )

    def finish_run(
        self,
        run_id: str,
        tenant_id: str,
        *,
        status: str,
        results: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Close a run as ``completed`` or ``failed``.

        Never leaves a run in ``running``: a permanently-running document is
        the failure mode that makes an eval dashboard useless, because it is
        indistinguishable from a run still in progress.
        """
        self._update_one(
            self.config.eval_runs_collection,
            {"tenant_id": tenant_id, "run_id": run_id},
            {
                "status": status,
                "results": results or {},
                "error": error,
                "finished_at": _now(),
            },
        )

    def list_runs(
        self,
        dataset_id: Optional[str] = None,
        limit: int = DEFAULT_RUN_LIMIT,
    ) -> List[Dict[str, Any]]:
        """List runs newest first, without their per-item rows."""
        identity = _require_admin()
        capped = max(1, min(int(limit or DEFAULT_RUN_LIMIT), MAX_RUN_LIMIT))
        filters: Dict[str, Any] = {"tenant_id": identity.tenant_id}
        if dataset_id:
            filters["dataset_id"] = dataset_id
        rows = self._query(
            self.config.eval_runs_collection,
            filters,
            sort=("started_at", -1),
            limit=capped,
        )
        return [_serialize({**_normalize_run(row), "per_item": []}) for row in rows]

    def get_run(self, run_id: str) -> Dict[str, Any]:
        """Return one run including its per-item rows.

        Raises:
            EvalNotFound: If no such run exists in the caller's tenant.
        """
        identity = _require_admin()
        document = self._find_one(
            self.config.eval_runs_collection,
            {"tenant_id": identity.tenant_id, "run_id": run_id},
        )
        if document is None:
            raise EvalNotFound(f"No eval run {run_id!r}")
        return _serialize(_normalize_run(document))

    # ------------------------------------------------------------------
    # Benchmark orchestrations
    # ------------------------------------------------------------------

    def create_benchmark_run(
        self,
        dataset_id: str,
        phases: List[Dict[str, Any]],
        progress: Dict[str, Any],
        *,
        dataset_version: Optional[int] = None,
        dataset_sha256: Optional[str] = None,
        manifest: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Open a benchmark document in ``queued`` state and return it.

        A benchmark is one ordered sequence of eval runs over a single
        dataset. It owns no scores of its own: each phase records the
        ``run_id`` of the ordinary eval run that produced them, so a phase
        result and a hand-started run are the same object read two ways.

        ``queued`` rather than ``running``: the document is written before
        the background task is scheduled, and a document that claimed to be
        running before anything was would be lying for as long as the event
        loop took to get to it.

        Args:
            dataset_id: The dataset every phase executes.
            phases: The phase plan from the orchestrator, already carrying
                each phase's support verdict.
            progress: The initial progress counters.
            dataset_version: The dataset's version at plan time.
            dataset_sha256: The dataset's fingerprint at plan time. Copied
                for the same reason a run copies it — the dataset may be
                edited before the last phase finishes, and a benchmark whose
                phases described different label sets would be uncomparable
                against itself.
            manifest: From
                :func:`app.services.benchmark_manifest.build_benchmark_manifest`
                — the build, dataset, retrieval, model and runtime metadata
                the benchmark is about to run under. Written once at plan
                time and never updated: it describes the conditions the
                phases started under, and rewriting it mid-benchmark would
                let a config change during a run erase the evidence that the
                run's own numbers came from the old one. ``None`` for a
                benchmark opened before manifests existed.
        """
        identity = _require_admin()
        document = {
            "benchmark_id": str(uuid4()),
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "dataset_sha256": dataset_sha256,
            "tenant_id": identity.tenant_id,
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "status": BENCHMARK_QUEUED,
            "phases": phases,
            "progress": progress,
            "manifest": manifest,
            "error": None,
        }
        self._insert(self.config.eval_benchmark_runs_collection, document)
        return _serialize(document)

    def record_benchmark_progress(
        self,
        benchmark_id: str,
        tenant_id: str,
        *,
        status: str,
        phases: List[Dict[str, Any]],
        progress: Dict[str, Any],
        started: bool = False,
    ) -> None:
        """Persist the phase table and counters as the benchmark advances.

        The whole ``phases`` array is written rather than one positional
        field: a single sequential orchestrator owns the document, so there
        is nothing to interleave with, and a whole-array write behaves
        identically on Mongo and on the in-memory store instead of relying
        on dotted-path semantics only one of them has.

        Takes ``tenant_id`` explicitly for the reason
        :meth:`append_item_result` does — the caller is a background task
        with no request context left to read an identity from.
        """
        changes: Dict[str, Any] = {
            "status": status,
            "phases": phases,
            "progress": progress,
        }
        if started:
            changes["started_at"] = _now()
        self._update_one(
            self.config.eval_benchmark_runs_collection,
            {"tenant_id": tenant_id, "benchmark_id": benchmark_id},
            changes,
        )

    def finish_benchmark_run(
        self,
        benchmark_id: str,
        tenant_id: str,
        *,
        status: str,
        phases: List[Dict[str, Any]],
        progress: Dict[str, Any],
        error: Optional[str] = None,
    ) -> None:
        """Close a benchmark in a terminal state.

        Never leaves it in ``running`` — including when the orchestrating
        task is cancelled, which closes it as ``interrupted``. A benchmark
        stuck in ``running`` is indistinguishable from one still working,
        which is exactly the state that makes a progress view useless.
        """
        self._update_one(
            self.config.eval_benchmark_runs_collection,
            {"tenant_id": tenant_id, "benchmark_id": benchmark_id},
            {
                "status": status,
                "phases": phases,
                "progress": progress,
                "error": error,
                "finished_at": _now(),
            },
        )

    def list_benchmark_runs(
        self,
        dataset_id: Optional[str] = None,
        limit: int = DEFAULT_RUN_LIMIT,
    ) -> List[Dict[str, Any]]:
        """List benchmarks newest first, scoped to the caller's tenant."""
        identity = _require_admin()
        capped = max(1, min(int(limit or DEFAULT_RUN_LIMIT), MAX_RUN_LIMIT))
        filters: Dict[str, Any] = {"tenant_id": identity.tenant_id}
        if dataset_id:
            filters["dataset_id"] = dataset_id
        rows = self._query(
            self.config.eval_benchmark_runs_collection,
            filters,
            sort=("created_at", -1),
            limit=capped,
        )
        return [_serialize(_normalize_benchmark(row)) for row in rows]

    def get_benchmark_run(self, benchmark_id: str) -> Dict[str, Any]:
        """Return one benchmark with its full phase table.

        Raises:
            EvalNotFound: If no such benchmark exists in the caller's tenant.
        """
        identity = _require_admin()
        document = self._find_one(
            self.config.eval_benchmark_runs_collection,
            {"tenant_id": identity.tenant_id, "benchmark_id": benchmark_id},
        )
        if document is None:
            raise EvalNotFound(f"No benchmark run {benchmark_id!r}")
        return _serialize(_normalize_benchmark(document))

    def _last_run_times(self, identity: AuthIdentity) -> Dict[str, Optional[str]]:
        """Map dataset_id to the ISO time of its most recent run.

        Both this and the dataset listing carry the tenant in their own
        first ``$match``; joining them afterwards is assembly, not filtering.
        """
        latest: Dict[str, Optional[str]] = {}
        for row in self._query(
            self.config.eval_runs_collection,
            {"tenant_id": identity.tenant_id},
            sort=("started_at", -1),
        ):
            dataset_id = row.get("dataset_id")
            if dataset_id not in latest:
                latest[dataset_id] = _iso(row.get("started_at"))
        return latest

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def ensure_indexes(self) -> None:
        """Create the tenant/time indexes on every eval collection."""
        if self._in_memory:
            return
        self._collection(self.config.eval_datasets_collection).create_index(
            [("tenant_id", 1), ("created_at", -1)],
            name="idx_eval_datasets_tenant_created",
        )
        self._collection(self.config.eval_runs_collection).create_index(
            [("tenant_id", 1), ("created_at", -1)],
            name="idx_eval_runs_tenant_created",
        )
        self._collection(self.config.eval_runs_collection).create_index(
            [("dataset_id", 1), ("started_at", -1)],
            name="idx_eval_runs_dataset_started",
        )
        self._collection(self.config.eval_benchmark_runs_collection).create_index(
            [("tenant_id", 1), ("created_at", -1)],
            name="idx_eval_benchmarks_tenant_created",
        )
        self._collection(self.config.eval_benchmark_runs_collection).create_index(
            [("dataset_id", 1), ("created_at", -1)],
            name="idx_eval_benchmarks_dataset_created",
        )

    def backfill_dataset_fingerprints(self) -> int:
        """Persist version/fingerprint on datasets written before versioning.

        Startup migration, idempotent and safe to run on every boot: it only
        touches documents missing one of the two fields, and it writes each
        document the same values :func:`_normalize_dataset` would have
        inferred for it on read. Nothing is recomputed for a dataset that
        already carries them — a stored fingerprint is the historical record,
        not a cache to be refreshed.

        It runs outside any request, so it takes no identity and asserts no
        tenant filter: it never returns dataset content, and each document
        receives only fields derived from its own items.

        Returns:
            How many datasets were migrated.
        """
        name = self.config.eval_datasets_collection
        scope = {
            "$or": [
                {"dataset_sha256": {"$in": [None, ""]}},
                {"dataset_version": {"$in": [None, 0]}},
            ]
        }
        migrated = 0
        if self._in_memory:
            for document in self._docs(name):
                if document.get("dataset_sha256") and document.get("dataset_version"):
                    continue
                document.update(_normalize_dataset(document))
                migrated += 1
            return migrated

        collection = self._collection(name)
        for document in collection.find(scope):
            normalized = _normalize_dataset(document)
            collection.update_one(
                {"_id": document["_id"]},
                {
                    "$set": {
                        "dataset_version": normalized["dataset_version"],
                        "dataset_sha256": normalized["dataset_sha256"],
                    }
                },
            )
            migrated += 1
        return migrated

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

    def _collection(self, name: str) -> Collection:
        self._init_db()
        return self._db[name]

    def _docs(self, name: str) -> List[Dict[str, Any]]:
        """The in-memory document list for one collection."""
        return self._memory.setdefault(name, [])

    def _insert(self, name: str, document: Dict[str, Any]) -> None:
        if self._in_memory:
            self._docs(name).append(document)
            return
        self._collection(name).insert_one(dict(document))

    def _query(
        self,
        name: str,
        filters: Dict[str, Any],
        *,
        sort: Optional[Tuple[str, int]] = None,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        """Run one equality query, sorted and limited in the datastore.

        ``filters`` becomes the pipeline's **first** ``$match``, which is
        where the tenant boundary has to live. The in-memory branch applies
        the identical predicate — it is the same query answered by a list.
        """
        if self._in_memory:
            rows = [
                document
                for document in self._docs(name)
                if all(document.get(key) == value for key, value in filters.items())
            ]
            if sort:
                field, direction = sort
                rows.sort(key=lambda row: _sort_key(row.get(field)), reverse=direction < 0)
            return rows[:limit] if limit else rows

        pipeline: List[Dict[str, Any]] = [{"$match": dict(filters)}]
        if sort:
            pipeline.append({"$sort": {sort[0]: sort[1]}})
        if limit:
            pipeline.append({"$limit": limit})
        pipeline.append({"$project": {"_id": 0}})
        return list(self._collection(name).aggregate(pipeline))

    def _find_one(self, name: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch one document under a tenant-scoped filter."""
        rows = self._query(name, filters, limit=1)
        return rows[0] if rows else None

    def _update_one(
        self,
        name: str,
        filters: Dict[str, Any],
        changes: Dict[str, Any],
        push: Optional[Tuple[str, Any]] = None,
    ) -> bool:
        """Apply ``$set`` and an optional ``$push`` under a scoped filter.

        Returns:
            Whether a document matched. False means the id does not exist in
            the caller's tenant — which the caller reports as not-found
            rather than as a silent no-op.
        """
        if self._in_memory:
            for document in self._docs(name):
                if all(document.get(key) == value for key, value in filters.items()):
                    document.update(changes)
                    if push:
                        document.setdefault(push[0], []).append(push[1])
                    return True
            return False

        update: Dict[str, Any] = {}
        if changes:
            update["$set"] = changes
        if push:
            update["$push"] = {push[0]: push[1]}
        if not update:
            return False
        result = self._collection(name).update_one(dict(filters), update)
        return result.matched_count > 0

    def _delete_one(self, name: str, filters: Dict[str, Any]) -> bool:
        if self._in_memory:
            for index, document in enumerate(self._docs(name)):
                if all(document.get(key) == value for key, value in filters.items()):
                    del self._docs(name)[index]
                    return True
            return False
        return self._collection(name).delete_one(dict(filters)).deleted_count > 0


def _sort_key(value: Any) -> Any:
    """Sort key that keeps None ordered last under a descending sort."""
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0 if value is None else value


def _iso(value: Any) -> Optional[str]:
    """Render a stored timestamp as ISO-8601, or None."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else None


def _normalize_dataset(document: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in the version and fingerprint of a pre-versioning dataset.

    Read-side migration, applied to every dataset on its way out of storage,
    so a dataset written before this feature existed stays readable and
    still reports a usable pair. It is not a write: a document is only
    updated in place by :meth:`EvalStore.backfill_dataset_fingerprints` or
    by the next :meth:`EvalStore.update_dataset`.

    The inferred version is :data:`INITIAL_DATASET_VERSION`, which is honest
    — the labels were never versioned, so nothing is known to have changed —
    and the inferred hash is computed from the items actually stored, so it
    matches what a fresh upload of the same labels would produce.
    """
    if document.get("dataset_sha256") and document.get("dataset_version"):
        return document
    return {
        **document,
        "dataset_version": int(document.get("dataset_version") or INITIAL_DATASET_VERSION),
        "dataset_sha256": document.get("dataset_sha256")
        or dataset_fingerprint(document.get("items")),
    }


def _normalize_run(document: Dict[str, Any]) -> Dict[str, Any]:
    """Make a pre-versioning run readable without inventing its provenance.

    Unlike a dataset, a run's missing fields stay ``None``. The dataset it
    scored may well have been edited since, so any value computed now would
    be a guess presented as evidence — and a wrong fingerprint on a historical
    run is worse than a blank one, which the UI can label "not recorded".
    """
    return {
        "dataset_version": None,
        "dataset_sha256": None,
        # A run recorded before pipeline mode was separated from evaluation
        # mode drove whatever the graph defaulted to. None says "not
        # recorded"; "regular" would be a guess dressed as provenance.
        "pipeline_mode": None,
        "benchmark_id": None,
        # None, not an empty result: a run recorded before stale-label
        # detection existed was never checked, and saying "no stale labels"
        # on its behalf would be a claim nobody made.
        "label_validation": None,
        **document,
    }


def _normalize_benchmark(document: Dict[str, Any]) -> Dict[str, Any]:
    """Make a pre-manifest benchmark readable without inventing provenance.

    For the reason :func:`_normalize_run` leaves its gaps at ``None``: a
    manifest built now would describe today's build and today's config, not
    the ones that benchmark actually ran under, and a confident wrong
    manifest is worse than a blank one a UI can label "not recorded".
    """
    return {"manifest": None, **document}


def _serialize(document: Dict[str, Any]) -> Dict[str, Any]:
    """Make one stored document JSON-safe for the RPC reply envelope."""
    serialized = {key: value for key, value in document.items() if key != "_id"}
    for field in ("created_at", "updated_at", "started_at", "finished_at"):
        if field in serialized:
            serialized[field] = _iso(serialized[field])
    return serialized


def create_eval_store(config: RAGConfig) -> EvalStore:
    """Create the eval store for the configured backend."""
    return EvalStore(config)
