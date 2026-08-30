"""Deterministic consolidation and conflict policy for memory writes.

This module decides what a new candidate does to the memories an owner
already holds. It is deliberately pure: it takes the normalized candidate
and a bounded, already-retrieved list of comparable memories, and returns a
decision. No I/O, no embedding, no LLM — the reasoning layer belongs to
MEMORY-AGENT-01, and a policy that cannot be replayed from its inputs cannot
be tested for the properties this task has to guarantee.

Two ideas drive the rules:

* Similarity alone never supersedes anything. Two memories can be worded
  almost identically and still be separate facts, so retiring an existing
  memory requires a declared ``fact_key`` — a caller saying "this is the same
  slot of truth" — or an explicit ``supersedes`` id. Everything else that
  looks related but is not provably the same fact is preserved and marked for
  review rather than silently merged or dropped.
* A fact is scoped. "Deployment goes to GCP" and "for the new environment,
  deployment moved to AWS" are not a contradiction when the second one names a
  scope the first does not; they coexist, and a query answers from the scope
  it asked about.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Consolidation outcomes. This vocabulary is bounded on purpose: it is used as
# a Prometheus label and as the contract every conflict test asserts against.
OUTCOME_CREATE = "create"
OUTCOME_DUPLICATE_EXACT = "duplicate_exact"
OUTCOME_DUPLICATE_SEMANTIC = "duplicate_semantic"
OUTCOME_SUPERSEDE = "supersede"
OUTCOME_COEXIST = "coexist"
OUTCOME_HISTORICAL = "historical"
OUTCOME_NEEDS_REVIEW = "needs_review"

CONSOLIDATION_OUTCOMES = {
    OUTCOME_CREATE,
    OUTCOME_DUPLICATE_EXACT,
    OUTCOME_DUPLICATE_SEMANTIC,
    OUTCOME_SUPERSEDE,
    OUTCOME_COEXIST,
    OUTCOME_HISTORICAL,
    OUTCOME_NEEDS_REVIEW,
}

# The comparison actually used to find candidates, reported so a caller can
# tell a semantic decision from one made on keyword overlap alone.
COMPARISON_SEMANTIC = "semantic"
COMPARISON_LEXICAL = "lexical"


def scope_key(scope: Any) -> str:
    """Return the canonical string identity of a memory's scope.

    Scopes are compared, never interpreted, so they collapse to a sorted
    ``k=v`` string. An absent or empty scope is the global scope ``""`` — the
    scope a plain fact with no qualifier belongs to.
    """
    if not isinstance(scope, dict) or not scope:
        return ""
    normalized = {
        str(key).strip().lower(): str(value).strip().lower()
        for key, value in scope.items()
        if str(key).strip() and str(value).strip()
    }
    return "&".join(f"{key}={normalized[key]}" for key in sorted(normalized))


@dataclass
class ConsolidationDecision:
    """What one candidate does to the memories already stored."""

    outcome: str
    reason: str
    target_id: Optional[str] = None
    similarity: Optional[float] = None
    comparison: str = COMPARISON_LEXICAL
    candidates_considered: int = 0
    related_ids: List[str] = field(default_factory=list)

    def as_provenance(self) -> Dict[str, Any]:
        """Return the diagnostic record stored on the resulting memory."""
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "target_id": self.target_id,
            "similarity": None if self.similarity is None else round(self.similarity, 6),
            "comparison": self.comparison,
            "candidates_considered": self.candidates_considered,
            "related_ids": list(self.related_ids),
        }


class ConsolidationPolicy:
    """Decide the outcome of one write against bounded existing memories."""

    def __init__(
        self,
        duplicate_threshold: float,
        conflict_threshold: float,
    ) -> None:
        self.duplicate_threshold = duplicate_threshold
        self.conflict_threshold = conflict_threshold

    @staticmethod
    def _ordered(
        candidates: Sequence[Tuple[Dict[str, Any], float]],
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Sort comparable memories most-similar first, ties broken by id.

        Determinism matters more than the tie order itself: the same corpus
        and the same candidate must always produce the same decision.
        """
        return sorted(candidates, key=lambda item: (-item[1], str(item[0].get("id") or "")))

    @staticmethod
    def _fact_key(doc: Dict[str, Any]) -> str:
        return str(doc.get("fact_key") or "").strip().lower()

    def decide(
        self,
        candidate: Dict[str, Any],
        comparable: Sequence[Tuple[Dict[str, Any], float]],
        *,
        comparison: str = COMPARISON_LEXICAL,
    ) -> ConsolidationDecision:
        """Return the deterministic outcome for one candidate.

        Args:
            candidate: The normalized candidate about to be written.
            comparable: ``(existing_memory, similarity)`` pairs, already bounded
                by the caller to the configured candidate limit and already
                restricted to the same owner, memory class and tenant scope.
            comparison: Whether ``similarity`` came from the vector index or
                from keyword overlap. Recorded, never used to change a rule.
        """
        ordered = self._ordered(comparable)
        considered = len(ordered)
        candidate_scope = scope_key(candidate.get("scope"))
        candidate_fact_key = self._fact_key(candidate)

        def decision(outcome: str, reason: str, doc: Optional[Dict[str, Any]] = None,
                     similarity: Optional[float] = None) -> ConsolidationDecision:
            return ConsolidationDecision(
                outcome=outcome,
                reason=reason,
                target_id=None if doc is None else str(doc.get("id")),
                similarity=similarity,
                comparison=comparison,
                candidates_considered=considered,
                related_ids=[str(doc.get("id")) for doc, _ in ordered if doc.get("id")],
            )

        # An explicit id the caller asked to replace outranks every inferred
        # rule: the caller already knows which fact it is updating.
        explicit_target = str(candidate.get("supersedes") or "").strip()
        if explicit_target:
            for doc, similarity in ordered:
                if str(doc.get("id")) == explicit_target:
                    return decision(OUTCOME_SUPERSEDE, "candidate explicitly supersedes this memory", doc, similarity)
            # The named memory was not among the compared candidates — it may
            # be less similar than the bound reached. The caller still resolves
            # the id under its own tenant scope, so naming an unreachable id
            # simply retires nothing.
            named = decision(OUTCOME_SUPERSEDE, "candidate explicitly supersedes a named memory")
            named.target_id = explicit_target
            return named

        # A candidate that already carries an end of validity is being written
        # as history, not as the current answer to anything.
        if candidate.get("valid_to"):
            return decision(OUTCOME_HISTORICAL, "candidate is written as a closed historical fact")

        for doc, _ in ordered:
            if (
                scope_key(doc.get("scope")) == candidate_scope
                and doc.get("content_hash")
                and doc["content_hash"] == candidate.get("content_hash")
            ):
                return decision(OUTCOME_DUPLICATE_EXACT, "identical active memory already stored", doc, 1.0)

        if not ordered:
            return decision(OUTCOME_CREATE, "no comparable memory found")

        # Scope partitions the comparison before similarity is consulted at
        # all. Comparing against the globally most similar memory would let a
        # candidate scoped to one environment retire an identically worded
        # fact belonging to another — the precise mistake scopes exist to
        # prevent, and one that only shows up when several scopes hold the
        # same sentence with a different value.
        in_scope = [pair for pair in ordered if scope_key(pair[0].get("scope")) == candidate_scope]
        out_of_scope = [pair for pair in ordered if scope_key(pair[0].get("scope")) != candidate_scope]

        if in_scope:
            best_doc, best_similarity = in_scope[0]
            same_fact = next(
                (
                    (doc, similarity)
                    for doc, similarity in in_scope
                    if candidate_fact_key and candidate_fact_key == self._fact_key(doc)
                ),
                None,
            )
            if same_fact is not None and same_fact[1] >= self.duplicate_threshold:
                return decision(
                    OUTCOME_DUPLICATE_SEMANTIC,
                    "near-identical memory already stored in the same scope",
                    same_fact[0],
                    same_fact[1],
                )
            if same_fact is not None:
                return decision(
                    OUTCOME_SUPERSEDE,
                    "same fact key in the same scope carries a new value",
                    same_fact[0],
                    same_fact[1],
                )
            if best_similarity >= self.duplicate_threshold:
                return decision(
                    OUTCOME_DUPLICATE_SEMANTIC,
                    "near-identical memory already stored in the same scope",
                    best_doc,
                    best_similarity,
                )
            if best_similarity >= self.conflict_threshold:
                # Similar, same scope, but nothing declares the two to be the
                # same slot of truth. Both are kept and the pair is flagged;
                # guessing here is how unrelated facts get silently merged.
                return decision(
                    OUTCOME_NEEDS_REVIEW,
                    "related memory found but no fact key declares them the same fact",
                    best_doc,
                    best_similarity,
                )

        if out_of_scope and out_of_scope[0][1] >= self.conflict_threshold:
            other_doc, other_similarity = out_of_scope[0]
            return decision(
                OUTCOME_COEXIST,
                "related memory belongs to a different scope and stays valid",
                other_doc,
                other_similarity,
            )

        best_doc, best_similarity = ordered[0]
        return decision(OUTCOME_CREATE, "no comparable memory passed the conflict threshold", best_doc, best_similarity)
