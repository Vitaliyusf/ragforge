"""Utilities for safe debug visibility and secret redaction."""
from __future__ import annotations

import re
from typing import Optional


_REDACTION_PATTERNS = (
    (
        re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,;]+)"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(x-api-key|api[_-]?key|token|secret|password)\b\s*[:=]\s*([\"']?)([^\"'\s,;]+)\2"),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^/\s:@]+):([^@\s/]+)@"),
        r"\1[REDACTED]@",
    ),
    (
        re.compile(r"\b(sk-[A-Za-z0-9_-]{10,})\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\b(lsv2_[A-Za-z0-9_-]{10,})\b"),
        "[REDACTED_SECRET]",
    ),
)


def redact_secrets(text: Optional[str]) -> str:
    """Redact common secret formats from debug-visible text."""
    if not text:
        return ""

    redacted = text
    for pattern, replacement in _REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def truncate_text(text: Optional[str], max_chars: int) -> str:
    """Truncate oversized text while preserving the number of omitted characters."""
    if not text:
        return ""
    if max_chars <= 0 or len(text) <= max_chars:
        return text

    omitted = len(text) - max_chars
    return f"{text[:max_chars]}...[TRUNCATED {omitted} chars]"


def sanitize_debug_text(text: Optional[str], max_chars: int) -> str:
    """Redact secrets first, then apply truncation."""
    return truncate_text(redact_secrets(text), max_chars)
