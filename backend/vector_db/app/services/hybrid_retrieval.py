"""Deterministic reciprocal-rank fusion for dense and sparse candidates."""
from __future__ import annotations

from typing import Any, Dict, List


def _candidate_id(candidate: Dict[str, Any]) -> str:
    payload = candidate.get("payload") or {}
    return str(payload.get("chunk_id") or candidate.get("id") or "")


def reciprocal_rank_fusion(
    dense: List[Dict[str, Any]],
    sparse: List[Dict[str, Any]],
    *,
    limit: int,
    rrf_k: int = 60,
) -> List[Dict[str, Any]]:
    """Fuse two ranked lists once, with stable ordering for equal scores."""
    if limit < 1 or rrf_k < 1:
        raise ValueError("limit and rrf_k must be positive")

    fused: Dict[str, Dict[str, Any]] = {}
    for arm, candidates in (("dense", dense), ("sparse", sparse)):
        for rank, candidate in enumerate(candidates, start=1):
            chunk_id = _candidate_id(candidate)
            if not chunk_id:
                continue
            entry = fused.setdefault(
                chunk_id,
                {
                    "candidate": dict(candidate),
                    "dense_rank": None,
                    "dense_score": None,
                    "sparse_rank": None,
                    "sparse_score": None,
                    "fused_score": 0.0,
                },
            )
            rank_key = f"{arm}_rank"
            if entry[rank_key] is not None:
                continue
            entry[rank_key] = rank
            entry[f"{arm}_score"] = candidate.get("score")
            entry["fused_score"] += 1.0 / (rrf_k + rank)

    ordered = sorted(
        fused.items(),
        key=lambda item: (
            -item[1]["fused_score"],
            min(
                rank
                for rank in (item[1]["dense_rank"], item[1]["sparse_rank"])
                if rank is not None
            ),
            item[0],
        ),
    )[:limit]

    results: List[Dict[str, Any]] = []
    for fused_rank, (_, entry) in enumerate(ordered, start=1):
        item = entry.pop("candidate")
        item["score"] = entry["fused_score"]
        item["retrieval_diagnostics"] = {
            **entry,
            "fused_rank": fused_rank,
            "matched_arms": [
                arm for arm in ("dense", "sparse") if entry[f"{arm}_rank"] is not None
            ],
        }
        results.append(item)
    return results
