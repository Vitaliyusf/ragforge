"""Deterministic token- and diversity-aware final context selection."""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Sequence, Set, Tuple


DEFAULT_CHARS_PER_TOKEN = 3.5
PASSAGE_SEPARATOR_TOKENS = 2
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def estimate_tokens(text: str) -> int:
    """Conservatively estimate tokens using the service's shared 3.5 ratio."""
    if not text:
        return 0
    return math.ceil(len(text) / DEFAULT_CHARS_PER_TOKEN)


def _text(chunk: Dict[str, Any]) -> str:
    return str(chunk.get("text") or chunk.get("chunk") or chunk.get("content") or "")


def _source_id(chunk: Dict[str, Any], index: int) -> str:
    return str(chunk.get("chunk_id") or chunk.get("id") or f"passage_{index + 1}")


def _source_key(chunk: Dict[str, Any], index: int) -> str:
    return str(
        chunk.get("document_id")
        or chunk.get("file_id")
        or chunk.get("source_name")
        or chunk.get("source")
        or _source_id(chunk, index)
    )


def passage_token_cost(chunk: Dict[str, Any], passage_number: int) -> int:
    """Estimate the complete numbered passage cost, including its locator."""
    source_id = _source_id(chunk, passage_number - 1)
    locator = chunk.get("page") if chunk.get("page") is not None else chunk.get("section")
    header = f"[{passage_number}] source={source_id}"
    if locator is not None:
        header += f" locator={locator}"
    return estimate_tokens(header) + estimate_tokens(_text(chunk)) + PASSAGE_SEPARATOR_TOKENS


def context_token_count(chunks: Sequence[Dict[str, Any]]) -> int:
    """Return the token estimate used to enforce the context budget."""
    return sum(passage_token_cost(chunk, index) for index, chunk in enumerate(chunks, 1))


def _normalized_text(text: str) -> str:
    return " ".join(text.casefold().split())


def _word_set(text: str) -> Set[str]:
    return set(_WORD_RE.findall(text.casefold()))


def _redundant(text: str, accepted: Sequence[Tuple[str, Set[str]]]) -> bool:
    normalized = _normalized_text(text)
    words = _word_set(text)
    for prior_normalized, prior_words in accepted:
        if normalized == prior_normalized:
            return True
        union = words | prior_words
        if len(words) >= 5 and len(prior_words) >= 5 and union:
            if len(words & prior_words) / len(union) >= 0.9:
                return True
    return False


def _score(chunk: Dict[str, Any]) -> float:
    try:
        value = chunk.get("reranker_score")
        return float(chunk.get("score", 0.0) if value is None else value)
    except (TypeError, ValueError):
        return 0.0


def _deduplicate(candidates: Sequence[Dict[str, Any]]) -> List[Tuple[int, Dict[str, Any]]]:
    unique: List[Tuple[int, Dict[str, Any]]] = []
    seen_ids: Set[str] = set()
    accepted_text: List[Tuple[str, Set[str]]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        text = _text(candidate)
        if not text:
            continue
        chunk_id = _source_id(candidate, index)
        if chunk_id in seen_ids or _redundant(text, accepted_text):
            continue
        seen_ids.add(chunk_id)
        accepted_text.append((_normalized_text(text), _word_set(text)))
        unique.append((index, candidate))
    return unique


def _truncate_to_budget(
    chunk: Dict[str, Any], budget: int, passage_number: int
) -> Dict[str, Any] | None:
    """Return a copied prefix that fits, or None when even metadata cannot fit."""
    original = _text(chunk)
    probe = dict(chunk)
    probe["text"] = ""
    fixed_cost = passage_token_cost(probe, passage_number)
    available = budget - fixed_cost
    if available <= 0:
        return None
    max_chars = int(available * DEFAULT_CHARS_PER_TOKEN)
    if max_chars <= 0:
        return None
    prefix = original[:max_chars].rstrip()
    if not prefix:
        return None
    probe["text"] = prefix
    probe["context_truncated"] = len(prefix) < len(original)
    while prefix and passage_token_cost(probe, passage_number) > budget:
        prefix = prefix[:-1].rstrip()
        probe["text"] = prefix
    return probe if prefix else None


def assemble_context(
    candidates: Sequence[Dict[str, Any]],
    *,
    token_budget: int,
    max_passages: int,
    diversity_score_tolerance: float,
) -> List[Dict[str, Any]]:
    """Select a stable, non-redundant and source-diverse passage list.

    Candidate retrieval order is the stable tie-breaker. The best remaining
    score always wins unless a new-source candidate is within the configured
    score tolerance; clearly stronger evidence is therefore never displaced
    merely to diversify the prompt.
    """
    if token_budget <= 0 or max_passages <= 0:
        return []

    remaining = _deduplicate(candidates)
    selected: List[Dict[str, Any]] = []
    selected_sources: Set[str] = set()
    used_tokens = 0

    while remaining and len(selected) < max_passages:
        ranked = sorted(remaining, key=lambda item: (-_score(item[1]), item[0]))
        best_index, best = ranked[0]
        best_score = _score(best)
        choice = (best_index, best)
        if _source_key(best, best_index) in selected_sources:
            diverse = [
                item
                for item in ranked
                if _source_key(item[1], item[0]) not in selected_sources
                and best_score - _score(item[1]) <= diversity_score_tolerance
            ]
            if diverse:
                choice = diverse[0]

        remaining.remove(choice)
        original_index, candidate = choice
        passage_number = len(selected) + 1
        cost = passage_token_cost(candidate, passage_number)
        available = token_budget - used_tokens
        if cost > available:
            if selected:
                continue
            truncated = _truncate_to_budget(candidate, available, passage_number)
            if truncated is None:
                continue
            candidate = truncated
            cost = passage_token_cost(candidate, passage_number)

        selected.append(dict(candidate))
        selected_sources.add(_source_key(candidate, original_index))
        used_tokens += cost

    return selected
