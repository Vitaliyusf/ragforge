"""Bounded per-item retrieval lineage: what was retrieved, when, and why.

An aggregate Recall@10 says a run got worse. It cannot say *where* an item
lost its answer — whether the relevant chunk was never a candidate, was a
candidate the merge demoted, or was retrieved and then dropped by the
eligibility gate. That question is answered per item, by the sequence of
retrieval steps the item actually went through, so this module records that
sequence and the eval runner binds it to the item's row.

**This extends the existing retrieval path rather than adding a second one**
(DEC-002). Nothing here retrieves, scores or ranks: a collector is handed to
the code that already does those things, that code reports what it just did,
and the collector shapes the report. A trace that computed anything of its
own would be a parallel retriever, and a diagnostic that disagrees with the
system it diagnoses is worse than none.

Three bounds are structural, not tuning knobs:

* **No chunk text, ever.** A candidate is an id, a rank and a score. Traces
  are stored on run documents and read by admins through the eval UI; letting
  private document text travel with them would turn a diagnostic into an
  exfiltration path.
* **Every list is capped.** Per-stage candidates, stage count and query
  length all truncate, and truncation is reported rather than hidden — a
  silently shortened lineage reads as "the chunk was never a candidate",
  which is the exact wrong conclusion.
* **Collection is opt-in.** A conversation turn with no collector does no
  trace work and returns no trace field, so a normal user payload is
  unchanged by this module's existence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# Stage names. Fixed strings rather than free text: a reader comparing two
# items' traces needs the same step to be called the same thing in both.
STAGE_BASE = "base"
STAGE_PASS_ONE = "pass_one"
STAGE_MERGED = "merged"
STAGE_PASS_TWO = "pass_two"
STAGE_FINAL_CONTEXT = "final_context"

# Why a candidate the store returned did not survive to the next step. These
# mirror the eligibility gate in `ConversationGraph._normalize_chunks` and
# `eval_runner.eligible_chunks` — the two places the policy is applied.
DROP_RETRIEVAL_NOT_ALLOWED = "retrieval_not_allowed"
DROP_REVIEW_REMOVED = "review_removed"

# Defaults used when a config carries no explicit bound. Deliberately small:
# a trace is a drill-down for one item, not a copy of the index.
DEFAULT_MAX_CANDIDATES = 20
DEFAULT_MAX_STAGES = 12
DEFAULT_MAX_QUERY_CHARS = 200


def _clean_id(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)


def _score(value: Any) -> Optional[float]:
    """A score the retriever reported, or ``None`` when it reported none.

    Never 0.0 for a missing score: an unmeasured rank must not read as a
    perfectly bad one.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _field(chunk: Dict[str, Any], name: str) -> Any:
    """Read one field from either the flat or the Qdrant-nested chunk shape."""
    payload = chunk.get("payload") or {}
    metadata = chunk.get("metadata") or payload.get("metadata") or {}
    value = chunk.get(name)
    if value not in (None, ""):
        return value
    value = payload.get(name)
    if value not in (None, ""):
        return value
    return metadata.get(name)


def candidate_view(chunk: Dict[str, Any], rank: int) -> Dict[str, Any]:
    """One candidate as it is stored: identity, position, score. No text."""
    view = {
        "rank": rank,
        "chunk_id": _clean_id(_field(chunk, "chunk_id")),
        "file_id": _clean_id(_field(chunk, "file_id") or _field(chunk, "document_id")),
        "score": _score(_field(chunk, "score")),
    }
    diagnostics = chunk.get("retrieval_diagnostics") or {}
    if diagnostics:
        view["retrieval"] = {
            "dense_rank": diagnostics.get("dense_rank"),
            "dense_score": _score(diagnostics.get("dense_score")),
            "sparse_rank": diagnostics.get("sparse_rank"),
            "sparse_score": _score(diagnostics.get("sparse_score")),
            "fused_rank": diagnostics.get("fused_rank"),
            "fused_score": _score(diagnostics.get("fused_score")),
            "matched_arms": list(diagnostics.get("matched_arms") or [])[:2],
        }
    return view


def candidate_views(chunks: Iterable[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Rank the given chunks in retrieval order, capped at ``limit``.

    Ranks are assigned before the cap, so a truncated list still says where
    in the full ranking each surviving candidate stood.
    """
    views: List[Dict[str, Any]] = []
    for rank, chunk in enumerate(chunks, 1):
        if rank > max(0, limit):
            break
        if isinstance(chunk, dict):
            views.append(candidate_view(chunk, rank))
    return views


def dropped_view(chunk: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """One refused candidate: which id, and which policy refused it."""
    return {"chunk_id": _clean_id(_field(chunk, "chunk_id")), "reason": reason}


@dataclass
class RetrievalTrace:
    """Collects one item's retrieval lineage under fixed bounds.

    Created per eval item and handed to whatever performs the retrieval. It
    is not thread-safe and is not meant to be shared between items: two items
    writing into one trace would produce a lineage that explains neither.
    """

    max_candidates: int = DEFAULT_MAX_CANDIDATES
    max_stages: int = DEFAULT_MAX_STAGES
    max_query_chars: int = DEFAULT_MAX_QUERY_CHARS
    stages: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    @classmethod
    def from_config(cls, config: Any) -> "RetrievalTrace":
        """Build a collector bounded by this deployment's trace limits."""
        return cls(
            max_candidates=int(
                getattr(config, "eval_trace_max_candidates", DEFAULT_MAX_CANDIDATES)
                or DEFAULT_MAX_CANDIDATES
            ),
            max_stages=int(
                getattr(config, "eval_trace_max_stages", DEFAULT_MAX_STAGES)
                or DEFAULT_MAX_STAGES
            ),
            max_query_chars=int(
                getattr(config, "eval_trace_max_query_chars", DEFAULT_MAX_QUERY_CHARS)
                or DEFAULT_MAX_QUERY_CHARS
            ),
        )

    def record_stage(
        self,
        stage: str,
        candidates: Iterable[Dict[str, Any]],
        *,
        query: Optional[str] = None,
        query_source: Optional[str] = None,
        requested_k: Optional[int] = None,
        returned_count: Optional[int] = None,
        dropped: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Record one retrieval step's ranked candidates.

        Args:
            candidates: The chunks this step yielded, already in the order
                the step produced them.
            returned_count: How many the store returned before eligibility
                filtering, when that differs from the number kept. Recorded
                separately so "filtered out" never looks like "never found".
            dropped: The candidates this step refused, each with its reason.
        """
        listed = [chunk for chunk in candidates if isinstance(chunk, dict)]
        views = candidate_views(listed, self.max_candidates)
        entry: Dict[str, Any] = {
            "stage": stage,
            "query": self._query(query),
            "query_source": query_source,
            "requested_k": requested_k,
            "returned_count": len(listed) if returned_count is None else int(returned_count),
            "kept_count": len(listed),
            "candidates": views,
            "candidates_truncated": len(views) < len(listed),
        }
        if entry["candidates_truncated"]:
            self.truncated = True
        if dropped:
            entry["dropped"] = [
                {"chunk_id": _clean_id(item.get("chunk_id")), "reason": item.get("reason")}
                for item in dropped[: self.max_candidates]
            ]
        stage_limit = max(1, self.max_stages)
        if stage == STAGE_FINAL_CONTEXT:
            # Terminal evidence is not an optional diagnostic stage: it is
            # the context generation actually used. Replace an older terminal
            # entry (defensive) and evict the least-recent diagnostic entry
            # when the generic bound is already full.
            self.stages = [
                recorded
                for recorded in self.stages
                if recorded.get("stage") != STAGE_FINAL_CONTEXT
            ]
            if len(self.stages) >= stage_limit:
                drop_index = next(
                    (
                        index
                        for index, recorded in enumerate(self.stages)
                        if recorded.get("stage")
                        not in {STAGE_BASE, STAGE_MERGED, STAGE_PASS_TWO}
                    ),
                    len(self.stages) - 1,
                )
                self.stages.pop(drop_index)
                self.truncated = True
            self.stages.append(entry)
            return
        if len(self.stages) >= stage_limit:
            # The lineage is longer than the bound. Flagged once rather than
            # dropping steps silently. A later final-context stage can still
            # displace one diagnostic entry.
            self.truncated = True
            return
        self.stages.append(entry)

    def final_context_stage(self) -> Optional[Dict[str, Any]]:
        """Return the mandatory terminal context entry, when recorded."""
        return next(
            (
                stage
                for stage in reversed(self.stages)
                if stage.get("stage") == STAGE_FINAL_CONTEXT
            ),
            None,
        )

    def record_decision(
        self,
        stage: str,
        decision: str,
        *,
        reason: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a branch the pipeline took — including one it did not take.

        A skipped second pass is a fact about the item, not an absence: it is
        why the item's ranking stopped changing.

        Only scalar details are kept. A branch's inputs are thresholds and
        scores; admitting arbitrary objects here is how document text would
        eventually arrive in a trace.
        """
        self.decisions.append(
            {
                "stage": stage,
                "decision": decision,
                "reason": reason,
                "detail": {
                    key: value
                    for key, value in (detail or {}).items()
                    if value is None or isinstance(value, (int, float, str, bool))
                },
            }
        )

    def _query(self, query: Optional[str]) -> Optional[str]:
        """The query a step ran, truncated to the configured bound."""
        if query is None:
            return None
        text = str(query)
        limit = max(0, self.max_query_chars)
        if len(text) <= limit:
            return text
        self.truncated = True
        return text[:limit] + "..."

    def provenance(self) -> List[Dict[str, Any]]:
        """Where each finally-selected chunk entered the ranking, and how it moved.

        Built from the stages already recorded rather than from a second
        source, so a chunk can never be reported as having arrived in a step
        the trace does not show.

        Empty until a :data:`STAGE_FINAL_CONTEXT` stage exists: before that
        there is no final selection to explain.
        """
        final = self.final_context_stage()
        if final is None:
            return []
        earlier = [stage for stage in self.stages if stage["stage"] != STAGE_FINAL_CONTEXT]
        rows: List[Dict[str, Any]] = []
        for candidate in final["candidates"]:
            chunk_id = candidate.get("chunk_id")
            ranks: Dict[str, int] = {}
            for stage in earlier:
                rank = next(
                    (
                        entry["rank"]
                        for entry in stage["candidates"]
                        if entry.get("chunk_id") == chunk_id
                    ),
                    None,
                )
                if rank is not None and stage["stage"] not in ranks:
                    ranks[stage["stage"]] = rank
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "file_id": candidate.get("file_id"),
                    "final_rank": candidate.get("rank"),
                    "first_seen_stage": next(iter(ranks), None),
                    "ranks_by_stage": ranks,
                }
            )
        return rows

    def to_payload(self) -> Dict[str, Any]:
        """The stored shape: stages, branches, provenance, truncation flag."""
        return {
            "stages": self.stages,
            "decisions": self.decisions,
            "provenance": self.provenance(),
            "truncated": self.truncated,
        }
