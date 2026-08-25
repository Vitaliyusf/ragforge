"""Pure information-retrieval metrics over ranked chunk-id lists.

No I/O, no configuration, no database. Every function takes ids and returns
a float, which is what makes the whole suite hand-checkable in
``test_retrieval_metrics.py``.

Conventions, stated because each one is a real choice and a silent
alternative would change every number this module produces:

**Binary relevance.** A chunk is relevant or it is not; there are no graded
judgments in v1. The ideal DCG is therefore the discounted sum of
``min(len(relevant), k)`` ones — the best ranking achievable given how many
relevant chunks exist, not a hypothetical ``k`` of them.

**An empty ``relevant`` set returns 0.0.** The functions stay total rather
than returning None or raising, but 0.0 here is a sentinel for "unlabelled",
not a measurement. The caller — :mod:`app.services.eval_runner` — is
responsible for **excluding** such items from any mean and reporting them as
``items_skipped``. Averaging them in would let a half-labelled dataset
quietly depress every score, which looks like a retrieval regression and is
not one.

**``k`` larger than ``len(retrieved)`` is well defined.** The list is not
padded and nothing is raised. Precision divides by how many chunks were
actually returned, so a retriever that returned two chunks and got one right
scores 0.5 at every ``k >= 2`` rather than decaying towards zero as ``k``
grows. Recall always divides by ``len(relevant)``, which is what makes it
recall.

**``k <= 0`` returns 0.0** — no window, nothing measured.

**Duplicates are removed first**, preserving first-occurrence order, by
:func:`dedupe`. A retriever returning the same chunk three times has found
one chunk; counting it three times would inflate precision and push the
first genuine miss down the ranking.
"""
from __future__ import annotations

from math import log2


def dedupe(retrieved: list[str]) -> list[str]:
    """Remove repeated ids, preserving first-occurrence order.

    Applied by every metric below before anything is counted. Public because
    the convention is worth asserting directly in the tests rather than only
    observing through its effects.

    Args:
        retrieved: Chunk ids in rank order, best first.

    Returns:
        The same ids with later repeats dropped.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for item in retrieved:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _top_k(retrieved: list[str], k: int) -> list[str]:
    """Return the de-duplicated top ``k``, or empty when ``k <= 0``."""
    if k <= 0:
        return []
    return dedupe(retrieved)[:k]


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Fraction of the relevant chunks that appear in the top ``k``.

    Args:
        retrieved: Chunk ids in rank order, best first.
        relevant: The ground-truth relevant chunk ids.
        k: Rank cutoff.

    Returns:
        A value in [0, 1]; 0.0 when ``relevant`` is empty — see the module
        docstring on why the caller must then exclude the item.
    """
    if not relevant:
        return 0.0
    top = _top_k(retrieved, k)
    return len(set(top) & relevant) / len(relevant)


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Fraction of the chunks considered at ``k`` that are relevant.

    The denominator is ``min(k, len(retrieved))``, not ``k``: the list is
    never padded, so a short result set is not penalised for positions that
    do not exist.

    Returns:
        A value in [0, 1]; 0.0 when nothing was retrieved or ``relevant`` is
        empty.
    """
    if not relevant:
        return 0.0
    top = _top_k(retrieved, k)
    if not top:
        return 0.0
    return len(set(top) & relevant) / len(top)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """Reciprocal of the rank of the first relevant chunk.

    Ranks are 1-based, so a hit in first place scores 1.0 and a hit at rank
    three scores 1/3. The mean of this over a dataset is MRR.

    Returns:
        1/rank of the first relevant chunk, or 0.0 if there is none.
    """
    if not relevant:
        return 0.0
    for rank, chunk_id in enumerate(dedupe(retrieved), start=1):
        if chunk_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Normalised discounted cumulative gain at ``k``, with binary gains.

    Unlike recall and precision this rewards ranking the relevant chunks
    *high*, not merely retrieving them: gain at rank ``i`` is discounted by
    ``1/log2(i + 1)``.

    Returns:
        A value in [0, 1]; 1.0 exactly when every relevant chunk within
        reach of ``k`` sits at the top of the ranking.
    """
    if not relevant:
        return 0.0
    top = _top_k(retrieved, k)
    if not top:
        return 0.0

    # Gain at rank i is discounted by 1/log2(i + 1), so a hit in first
    # place is undiscounted.
    dcg = sum(
        1.0 / log2(rank + 1)
        for rank, chunk_id in enumerate(top, start=1)
        if chunk_id in relevant
    )

    # Binary relevance: the ideal ranking is min(len(relevant), k) ones at
    # the top. Using k alone would make a perfect ranking of two relevant
    # chunks score below 1.0 at k=10 purely because only two exist.
    ideal_count = min(len(relevant), k)
    idcg = sum(1.0 / log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / idcg if idcg else 0.0


def hit_rate_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Whether any relevant chunk appears in the top ``k``.

    Per item this is 0.0 or 1.0; averaged over a dataset it is the share of
    queries for which retrieval found anything usable at all.
    """
    if not relevant:
        return 0.0
    return 1.0 if set(_top_k(retrieved, k)) & relevant else 0.0
