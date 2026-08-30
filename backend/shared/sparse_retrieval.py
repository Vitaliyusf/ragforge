"""Deterministic bounded lexical vectors shared by indexing and query paths."""
from __future__ import annotations

from collections import Counter
from hashlib import blake2b
from math import log1p, sqrt
import re
from typing import Dict, List


MAX_SPARSE_TERMS = 512
MAX_SPARSE_TEXT_CHARS = 20_000
_TOKEN_RE = re.compile(r"[^\W_]+(?:[._:/-][^\W_]+)*", re.UNICODE)


def sparse_lexical_vector(
    text: str,
    *,
    max_terms: int = MAX_SPARSE_TERMS,
) -> Dict[str, List[float] | List[int]]:
    """Return a stable unit-length hashed term-frequency vector.

    Unicode ``casefold`` preserves Hebrew tokens and normalizes Latin terms.
    Hashing keeps Qdrant indices bounded without a corpus vocabulary, while
    log-scaled term frequency prevents repeated boilerplate dominating a hit.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if max_terms < 1:
        raise ValueError("max_terms must be positive")

    counts = Counter(
        match.group(0).casefold()
        for match in _TOKEN_RE.finditer(text[:MAX_SPARSE_TEXT_CHARS])
    )
    if not counts:
        return {"indices": [], "values": []}

    hashed: Counter[int] = Counter()
    for token, count in counts.items():
        index = int.from_bytes(
            blake2b(token.encode("utf-8"), digest_size=4).digest(), "big"
        ) & 0x7FFFFFFF
        hashed[index] += count

    weighted = [(index, 1.0 + log1p(count)) for index, count in hashed.items()]
    weighted.sort(key=lambda item: (-item[1], item[0]))
    weighted = weighted[:max_terms]
    norm = sqrt(sum(value * value for _, value in weighted)) or 1.0
    weighted.sort(key=lambda item: item[0])
    return {
        "indices": [index for index, _ in weighted],
        "values": [value / norm for _, value in weighted],
    }
