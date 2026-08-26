"""Say which RAG stage lost an item, from that item's own recorded evidence.

A run that reports Recall@10 = 0.62 has named a symptom. The next question is
always the same — *where* did the other 38% go? — and answering it by opening
traces one item at a time does not scale past a demo. This module answers it
mechanically: every scored item is sorted into exactly one stage-shaped
category from the lineage :mod:`app.services.retrieval_trace` already
recorded, and :func:`aggregate_attribution` counts the categories over a run.

Three rules decide what may be claimed here:

**Nothing is inferred by a model.** Every category below is reached by
comparing recorded ids, counts and branch decisions. Asking an LLM which
stage failed would produce a confident sentence about a retrieval it never
observed, and a wrong attribution is worse than none: it sends whoever reads
it to tune the wrong knob.

**Insufficient evidence is a category, not a guess.** An item with no trace,
a truncated candidate list or an unjudged answer yields
:data:`CATEGORY_UNCLASSIFIED`. In particular, "the labelled chunk never
appears in the trace" only means "it was never a candidate" when the trace is
known to be complete — a truncated list says the same thing and means nothing.

**One item, one category.** The ladder in :func:`classify_item` is ordered
from the earliest stage that can be proven to the latest, so an item is
attributed to the *first* place its evidence breaks. Counting an item under
both "never retrieved" and "answer ungrounded" would double the denominator
and let a single bad query dominate two panels.

The categories are the pipeline's own stages, plus the two states that are
not retrieval failures at all — stale labels and a raised item — which are
kept separate so they never inflate a retrieval regression.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.retrieval_trace import STAGE_FINAL_CONTEXT, STAGE_PASS_TWO

# ── Categories ────────────────────────────────────────────────────────────

# The item was never retrieved for: its ground truth names ids the live index
# cannot return. A dataset problem, deliberately not a retrieval one.
CATEGORY_STALE_LABELS = "stale_labels"
# The item raised before it finished. Where it died is in its partial trace;
# that it died is not evidence about any stage's quality.
CATEGORY_PIPELINE_ERROR = "pipeline_error"
# Every retrieval step came back empty. Nothing ranked because nothing was
# returned — an index, embedding or filter problem, not a ranking one.
CATEGORY_INDEX = "index"
# The store returned candidates but never the labelled one, and the trace is
# complete enough to say so.
CATEGORY_RETRIEVAL = "retrieval"
# The labelled chunk *was* a candidate and did not survive to the context:
# the merge, the rerank or the depth cap dropped it.
CATEGORY_RANKING = "ranking"
# The second pass that might have found it was skipped, and the first pass
# never produced it. The branch is the failure.
CATEGORY_PASS_TWO = "pass_two"
# The labelled chunk was retrieved and then refused by the eligibility gate —
# review status or retrieval_allowed. "Retrieved then barred" reads
# identically to "never found" in a score and is a different fix.
CATEGORY_CONTEXT = "context"
# Retrieval found the labelled chunks; the model produced no answer from them.
CATEGORY_GENERATION = "generation"
# Some labelled ids were retrieved and some were not. The stage is right, the
# coverage is not.
CATEGORY_COMPLETENESS = "completeness"
# The context was right and the answer was not supported by it.
CATEGORY_GROUNDING = "grounding"
# The evidence does not support any of the above.
CATEGORY_UNCLASSIFIED = "unclassified"
# No failure evidence. Not a failure category and never counted as one.
CATEGORY_NONE = "none"
# The item was never labelled, so it has no expectation to have failed.
CATEGORY_NOT_APPLICABLE = "not_applicable"

# Every category a run counts, in ladder order. `none` and `not_applicable`
# are excluded: they are the absence of a failure, and a chart whose largest
# bar is "nothing went wrong" hides the bars that matter.
FAILURE_CATEGORIES: Tuple[str, ...] = (
    CATEGORY_INDEX,
    CATEGORY_RETRIEVAL,
    CATEGORY_PASS_TWO,
    CATEGORY_RANKING,
    CATEGORY_CONTEXT,
    CATEGORY_COMPLETENESS,
    CATEGORY_GENERATION,
    CATEGORY_GROUNDING,
    CATEGORY_STALE_LABELS,
    CATEGORY_PIPELINE_ERROR,
    CATEGORY_UNCLASSIFIED,
)

# Why an item could not be attributed. Stored on the item so a large
# unclassified count can be acted on rather than only stared at.
REASON_NO_TRACE = "no_trace"
REASON_TRUNCATED_CANDIDATES = "truncated_candidates"
REASON_ANSWER_UNJUDGED = "answer_unjudged"

# How many ids one item's evidence keeps. The evidence points at the
# drill-down; it is not a copy of it, and every item row is stored per run.
MAX_EVIDENCE_IDS = 5


def _ids(values: Any) -> List[str]:
    return [str(value) for value in (values or [])]


def _evidence_ids(values: Any) -> List[str]:
    """A bounded id list for storage, sorted so two runs compare cleanly."""
    return sorted(set(_ids(values)))[:MAX_EVIDENCE_IDS]


def _stage_ids(stage: Dict[str, Any]) -> Set[str]:
    """Every id one recorded stage's candidates can be matched on.

    Both id kinds are collected because an item is scored on whichever its
    dataset labelled — chunk ids for a chunk-level golden set, file ids for a
    file-level one — and the trace records both for the same candidate.
    """
    found: Set[str] = set()
    for candidate in stage.get("candidates") or []:
        for key in ("chunk_id", "file_id"):
            value = candidate.get(key)
            if value:
                found.add(str(value))
    return found


def _dropped_reasons(stages: List[Dict[str, Any]], missing: Set[str]) -> Dict[str, str]:
    """Which of the missing ids the eligibility gate refused, and why.

    Only chunk ids can be matched here: a refusal is recorded by chunk id, so
    a file-level golden set gets no gate evidence and its item falls through
    to the next rung rather than being attributed on a coincidence.
    """
    reasons: Dict[str, str] = {}
    for stage in stages:
        for entry in stage.get("dropped") or []:
            chunk_id = entry.get("chunk_id")
            if chunk_id and str(chunk_id) in missing:
                reasons.setdefault(str(chunk_id), str(entry.get("reason") or "unknown"))
    return reasons


def _retrieval_stages(stages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The steps that actually queried the store.

    ``final_context`` is excluded: it is a projection of what earlier steps
    produced, so counting its candidates as store results would report one
    retrieval twice.
    """
    return [stage for stage in stages if stage.get("stage") != STAGE_FINAL_CONTEXT]


def _returned_total(stages: List[Dict[str, Any]]) -> Optional[int]:
    """How many candidates the store returned across every retrieval step.

    ``None`` when no step reported a count — unmeasured, which must not read
    as "the index returned nothing".
    """
    counts = [
        int(stage["returned_count"])
        for stage in stages
        if isinstance(stage.get("returned_count"), int)
    ]
    return sum(counts) if counts else None


def _candidates_truncated(stages: List[Dict[str, Any]]) -> bool:
    """Whether any step's candidate list was cut short.

    The trace's own ``truncated`` flag is deliberately not used: it also
    fires for a long query, which says nothing about whether a chunk was a
    candidate, and treating that as missing evidence would push honest
    attributions into ``unclassified``.
    """
    return any(bool(stage.get("candidates_truncated")) for stage in stages)


def _pass_two_skip(trace: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The recorded decision to skip the second pass, if it was skipped."""
    for entry in trace.get("decisions") or []:
        decision: Dict[str, Any] = entry
        if decision.get("stage") == STAGE_PASS_TWO and decision.get("decision") == "skipped":
            return decision
    return None


def _attribution(category: str, **evidence: Any) -> Dict[str, Any]:
    """One item's verdict: the category, and what proved it."""
    return {"category": category, "evidence": dict(evidence)}


def classify_item(row: Dict[str, Any]) -> Dict[str, Any]:
    """Attribute one item row to the stage its own evidence blames.

    Args:
        row: A per-item result row as :mod:`app.services.eval_runner` writes
            it, including its bounded ``retrieval_trace``.

    Returns:
        ``{"category": ..., "evidence": {...}}``. The evidence carries ids,
        counts and branch reasons — never chunk or answer text, because item
        rows are read by every admin who opens the run.
    """
    if row.get("unscorable"):
        return _attribution(CATEGORY_STALE_LABELS, reason="labels_unreachable")
    if row.get("error"):
        stages = (row.get("retrieval_trace") or {}).get("stages") or []
        return _attribution(
            CATEGORY_PIPELINE_ERROR,
            stages_recorded=len(stages),
            last_stage=(stages[-1].get("stage") if stages else None),
        )

    expected = set(_ids(row.get("expected_ids")))
    if not expected or row.get("skipped"):
        return _attribution(CATEGORY_NOT_APPLICABLE, reason="unlabelled")

    retrieved = set(_ids(row.get("retrieved_ids")))
    missing = expected - retrieved
    if not missing:
        return _answer_attribution(row)
    if expected & retrieved:
        # A partial hit is a coverage failure at whatever stage produced the
        # ids that did land. Walking further down the ladder would blame a
        # stage that demonstrably worked for this same query.
        return _attribution(
            CATEGORY_COMPLETENESS,
            missing_ids=_evidence_ids(missing),
            expected_count=len(expected),
            retrieved_expected_count=len(expected & retrieved),
        )
    return _retrieval_attribution(row, missing)


def _answer_attribution(row: Dict[str, Any]) -> Dict[str, Any]:
    """Judge an item whose retrieval found every labelled id.

    A ``retrieval`` run stops here with :data:`CATEGORY_NONE`: it never
    called a model, so it holds no evidence about answers and must not
    manufacture any.
    """
    if "answer" not in row:
        return _attribution(CATEGORY_NONE)
    if not str(row.get("answer") or "").strip():
        return _attribution(CATEGORY_GENERATION, reason="empty_answer")
    verdict = row.get("hallucination_verdict")
    if verdict is None:
        # The judge did not return. Whether this answer was grounded is
        # unknown, and unknown is not "fine".
        return _attribution(CATEGORY_UNCLASSIFIED, reason=REASON_ANSWER_UNJUDGED)
    if verdict != "none":
        return _attribution(
            CATEGORY_GROUNDING,
            hallucination_verdict=verdict,
            unsupported_claim_count=row.get("unsupported_claim_count"),
        )
    return _attribution(CATEGORY_NONE)


def _retrieval_attribution(row: Dict[str, Any], missing: Set[str]) -> Dict[str, Any]:
    """Attribute an item none of whose labelled ids reached the context.

    The rungs are ordered by how strong their evidence is: a recorded gate
    refusal names the chunk and the policy, a candidate appearance names the
    stage, and "never a candidate" is only claimed once the trace is known to
    be complete enough to support it.
    """
    trace = row.get("retrieval_trace") or {}
    stages = trace.get("stages") or []
    if not stages:
        return _attribution(
            CATEGORY_UNCLASSIFIED,
            reason=REASON_NO_TRACE,
            missing_ids=_evidence_ids(missing),
        )

    dropped = _dropped_reasons(stages, missing)
    if dropped:
        return _attribution(
            CATEGORY_CONTEXT,
            missing_ids=_evidence_ids(dropped),
            drop_reasons=sorted(set(dropped.values())),
        )

    retrieval_stages = _retrieval_stages(stages)
    seen_in = [
        str(stage.get("stage"))
        for stage in retrieval_stages
        if _stage_ids(stage) & missing
    ]
    if seen_in:
        return _attribution(
            CATEGORY_RANKING,
            missing_ids=_evidence_ids(missing),
            candidate_stages=sorted(set(seen_in)),
        )

    returned = _returned_total(retrieval_stages)
    if returned == 0:
        return _attribution(
            CATEGORY_INDEX,
            missing_ids=_evidence_ids(missing),
            stages_searched=len(retrieval_stages),
        )
    if _candidates_truncated(stages):
        # The chunk is absent from a list that was cut short, so its absence
        # proves nothing about a ranking it never got to be compared in.
        return _attribution(
            CATEGORY_UNCLASSIFIED,
            reason=REASON_TRUNCATED_CANDIDATES,
            missing_ids=_evidence_ids(missing),
        )
    skipped = _pass_two_skip(trace)
    if skipped is not None:
        return _attribution(
            CATEGORY_PASS_TWO,
            missing_ids=_evidence_ids(missing),
            skip_reason=skipped.get("reason"),
            top_score=(skipped.get("detail") or {}).get("top_score"),
        )
    return _attribution(
        CATEGORY_RETRIEVAL,
        missing_ids=_evidence_ids(missing),
        stages_searched=len(retrieval_stages),
        candidates_returned=returned,
    )


def attribute_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Classify every row, for a caller aggregating rows it did not write."""
    return [classify_item(row) for row in rows]


def aggregate_attribution(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Count the per-item categories over one run.

    Each row's own ``failure_attribution`` is reused when it carries one, so
    the aggregate can never disagree with the drill-down beside it.

    ``rates`` divides by the items that *could* have failed — unlabelled
    items are excluded from the denominator rather than counted as passes.
    Every rate is ``None`` when that denominator is zero: a run with nothing
    to attribute has no measured rates, and printing ``0%`` for one would
    claim a clean run nobody measured.
    """
    counts: Dict[str, int] = {category: 0 for category in FAILURE_CATEGORIES}
    attributed = 0
    passed = 0
    for row in rows:
        verdict = row.get("failure_attribution") or classify_item(row)
        category = verdict.get("category")
        if category == CATEGORY_NOT_APPLICABLE:
            continue
        attributed += 1
        if category == CATEGORY_NONE:
            passed += 1
        elif category in counts:
            counts[category] += 1
    return {
        "counts": counts,
        "rates": {
            category: (counts[category] / attributed) if attributed else None
            for category in FAILURE_CATEGORIES
        },
        "items_attributed": attributed,
        "items_without_failure": passed,
        "items_failed_attributed": attributed - passed - counts[CATEGORY_UNCLASSIFIED],
        "items_unclassified": counts[CATEGORY_UNCLASSIFIED],
    }
