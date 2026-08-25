"""Pure citation-quality metrics over one answer's citations and judged claims.

No I/O, no configuration, no database — the same shape as
:mod:`app.services.retrieval_metrics`, and for the same reason: every number
here must be hand-checkable in ``test_citation_metrics.py``.

"Citation precision" and "citation recall" are used loosely in the
literature, so the conventions this module commits to are spelled out. An
undocumented convention would make every figure on the Quality panel
unauditable.

**Citation precision** — of the distinct passages the answer cited, the
fraction the judge confirmed actually support a claim. It answers *are the
citations honest?* A citation to a passage that supports nothing the answer
said is wrong even if the answer itself is correct.

**Citation recall** — of the claims the judge found *supportable from the
retrieved context*, the fraction the answer actually credited by citing one
of that claim's supporting passages. It answers *did the answer credit its
sources?* Claims the judge marked unsupported are outside the denominator:
they cannot be credited to a source, and counting them would turn a
hallucination into a citation failure, which is a different fault reported
separately as ``hallucination_verdict``.

**Denominator conventions.** An answer that cited nothing has precision
``None``, not ``0.0``; an answer with no supportable claims has recall
``None``. Averaging a ``0.0`` in either place conflates *cited badly* with
*did not cite*, which are different failures with different fixes. Every
aggregate here excludes ``None`` and reports how many it excluded, via
:func:`aggregate_mean` — a mean without its denominator is not a
measurement.

**Duplicates are counted once.** An answer citing ``[2]`` three times has
cited one passage.

**Passage-id namespace.** ``cited_ids`` and the judge's
``supporting_passage_ids`` must be expressed in the same namespace — both
resolved to retrieved chunk ids, or both left as prompt passage numbers.
Mixing the two silently scores every citation as wrong.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


def _distinct(ids: Iterable[str]) -> Set[str]:
    """Return the distinct, non-empty ids from an iterable."""
    return {str(item) for item in ids if item is not None and str(item) != ""}


def supporting_passage_ids(claims: Sequence[Dict[str, Any]]) -> Set[str]:
    """Return the passage ids the judge confirmed support some claim.

    Only claims marked supported contribute. A passage the judge listed
    against a claim it then called unsupported has not been confirmed to
    support anything.

    Args:
        claims: The judge's claim list. Malformed entries are ignored rather
            than raising — a badly shaped claim must not cost the turn its
            other measurements.

    Returns:
        The set of confirmed supporting passage ids.
    """
    confirmed: Set[str] = set()
    for claim in claims or []:
        if not isinstance(claim, dict) or not claim.get("supported"):
            continue
        confirmed |= _distinct(claim.get("supporting_passage_ids") or [])
    return confirmed


def resolve_claim_passage_ids(
    claims: Sequence[Dict[str, Any]],
    passage_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    """Rewrite a judge's passage references into the chunk-id namespace.

    The judge is shown passages numbered ``[1]``, ``[2]``, ... and answers
    in those numbers, while an answer's citations resolve to chunk ids.
    Comparing the two namespaces directly scores every honest citation as
    wrong, so one of them has to be translated, and this is where.

    A reference that is already a known chunk id is kept as-is; a number
    outside ``1..len(passage_ids)`` is dropped rather than guessed at.

    Args:
        claims: The judge's claim list.
        passage_ids: Chunk ids in the order the passages were numbered.

    Returns:
        New claim dicts with ``supporting_passage_ids`` in chunk-id terms.
    """
    known = set(passage_ids)
    resolved: List[Dict[str, Any]] = []
    for claim in claims or []:
        if not isinstance(claim, dict):
            continue
        ids: List[str] = []
        for raw in claim.get("supporting_passage_ids") or []:
            reference = str(raw).strip().strip("[]")
            if reference in known:
                if reference not in ids:
                    ids.append(reference)
                continue
            if reference.isdigit():
                index = int(reference)
                if 1 <= index <= len(passage_ids):
                    chunk_id = passage_ids[index - 1]
                    if chunk_id not in ids:
                        ids.append(chunk_id)
        entry = dict(claim)
        entry["supporting_passage_ids"] = ids
        resolved.append(entry)
    return resolved


def citation_precision(
    cited_ids: List[str],
    supporting_ids: Set[str],
) -> Optional[float]:
    """Fraction of the distinct cited passages that support a claim.

    Args:
        cited_ids: Passage ids the answer cited, in any order. Repeats count
            once.
        supporting_ids: Passage ids the judge confirmed as supporting — see
            :func:`supporting_passage_ids`.

    Returns:
        A value in [0, 1], or None when the answer cited nothing. None means
        unmeasured, not zero; see the module docstring.
    """
    cited = _distinct(cited_ids)
    if not cited:
        return None
    return len(cited & _distinct(supporting_ids)) / len(cited)


def citation_recall(
    claims: List[Dict[str, Any]],
    cited_ids: Optional[Set[str]] = None,
) -> Optional[float]:
    """Fraction of the supportable claims the answer credited to a source.

    A claim is *supportable* when the judge marked it supported and named at
    least one supporting passage. It is *credited* when the answer cited any
    of those passages.

    Args:
        claims: The judge's claim list.
        cited_ids: Passage ids the answer cited. When omitted, each claim's
            own boolean ``cited`` flag is used instead, for callers that
            resolved crediting upstream.

    Returns:
        A value in [0, 1], or None when no claim was supportable.
    """
    cited = None if cited_ids is None else _distinct(cited_ids)
    supportable = 0
    credited = 0
    for claim in claims or []:
        if not isinstance(claim, dict) or not claim.get("supported"):
            continue
        passage_ids = _distinct(claim.get("supporting_passage_ids") or [])
        if not passage_ids:
            continue
        supportable += 1
        if cited is None:
            if bool(claim.get("cited")):
                credited += 1
        elif passage_ids & cited:
            credited += 1
    if not supportable:
        return None
    return credited / supportable


def citation_f1(
    precision: Optional[float],
    recall: Optional[float],
) -> Optional[float]:
    """Harmonic mean of citation precision and recall.

    Args:
        precision: As returned by :func:`citation_precision`.
        recall: As returned by :func:`citation_recall`.

    Returns:
        The F1, 0.0 when both inputs are 0.0, or None when either input is
        None — half a measurement is not a measurement.
    """
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def cited_chunk_ratio(
    cited_ids: List[str],
    retrieved_chunk_count: int,
) -> Optional[float]:
    """Share of the retrieved chunks the answer cited.

    Coverage, not correctness: it says how much of what was retrieved the
    answer drew on, and says nothing about whether those citations were
    honest.

    Args:
        cited_ids: Passage ids the answer cited. Repeats count once.
        retrieved_chunk_count: How many chunks were put in front of the model.

    Returns:
        A value in [0, 1], or None when nothing was retrieved — a share of
        zero chunks is undefined, not zero. Capped at 1.0 so a citation to a
        passage outside the retrieved set cannot report more chunks cited
        than existed.
    """
    if not retrieved_chunk_count:
        return None
    return min(1.0, len(_distinct(cited_ids)) / retrieved_chunk_count)


def aggregate_mean(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    """Mean of the measured values, with the count of excluded Nones.

    The excluded count travels with the mean everywhere it is displayed: a
    precision of 1.0 over two answers and one over two hundred are different
    claims about the system.

    Args:
        values: Per-answer values, where None means unmeasured.

    Returns:
        ``{"mean": float | None, "counted": int, "excluded": int}``.
    """
    measured = [float(value) for value in values if value is not None]
    excluded = len(values) - len(measured)
    return {
        "mean": (sum(measured) / len(measured)) if measured else None,
        "counted": len(measured),
        "excluded": excluded,
    }
