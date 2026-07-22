"""Heuristic issue detector for review-gating during file ingestion."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.core.config import Settings

PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "disregard all prior instructions",
    "system prompt",
    "developer message",
    "reveal the hidden instructions",
)
UNSAFE_CONTENT_PATTERNS = (
    "how to make a bomb",
    "build an explosive",
    "terrorist attack",
    "commit murder",
    "harm a child",
)
PII_PATTERNS = (
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("payment_card", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
)


class IssueDetector:
    """Heuristic detector for review-gating findings in extracted text."""

    def __init__(self, config: Settings):
        self.config = config

    def detect(self, text: str, diagnostics: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        findings.extend(self._detect_prompt_injection(text))
        findings.extend(self._detect_pii(text))
        findings.extend(self._detect_unsafe_content(text))
        findings.extend(self._detect_parser_problem(text, diagnostics or {}))
        return findings

    def _detect_prompt_injection(self, text: str) -> List[Dict[str, Any]]:
        lowered = text.lower()
        for phrase in PROMPT_INJECTION_PATTERNS:
            index = lowered.find(phrase)
            if index >= 0:
                return [{
                    "category": "prompt_injection_risk",
                    "score": 0.95,
                    "threshold": self.config.prompt_injection_threshold,
                    "title": "Prompt injection risk detected",
                    "problem_description": "The extracted text appears to contain instruction-like content aimed at manipulating downstream models.",
                    "why_problematic": "This content can alter model behavior if embedded or surfaced without review.",
                    "text_span": {"start": index, "end": index + len(phrase)},
                    "detector": "prompt_phrase_v1",
                }]
        return []

    def _detect_pii(self, text: str) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        for label, pattern in PII_PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append({
                    "category": "pii_high_risk",
                    "score": 0.95,
                    "threshold": self.config.pii_high_risk_threshold,
                    "title": "High-risk PII detected",
                    "problem_description": f"Potentially sensitive {label.replace('_', ' ')} data was detected in the extracted text.",
                    "why_problematic": "Sensitive data should not be embedded or retrieved without human review.",
                    "text_span": {"start": match.start(), "end": match.end()},
                    "detector": "pii_regex_v1",
                })
        return findings[:3]

    def _detect_unsafe_content(self, text: str) -> List[Dict[str, Any]]:
        lowered = text.lower()
        for phrase in UNSAFE_CONTENT_PATTERNS:
            index = lowered.find(phrase)
            if index >= 0:
                return [{
                    "category": "unsafe_or_prohibited_content",
                    "score": 0.92,
                    "threshold": self.config.unsafe_content_threshold,
                    "title": "Unsafe or prohibited content detected",
                    "problem_description": "The extracted text appears to describe harmful or prohibited content.",
                    "why_problematic": "This content may violate policy and should be reviewed before ingestion continues.",
                    "text_span": {"start": index, "end": index + len(phrase)},
                    "detector": "unsafe_phrase_v1",
                }]
        return []

    def _detect_parser_problem(self, text: str, diagnostics: Dict[str, Any]) -> List[Dict[str, Any]]:
        stripped = (text or "").strip()
        warnings = diagnostics.get("warnings") or []
        if not stripped:
            return [{
                "category": "parser_or_format_problem",
                "score": 0.99,
                "threshold": self.config.parser_problem_threshold,
                "title": "Parser or format problem detected",
                "problem_description": "The extractor returned no usable text.",
                "why_problematic": "The file could not be ingested safely because the extracted text is empty.",
                "text_span": {"start": 0, "end": 0},
                "detector": "empty_text_v1",
            }]
        replacement_ratio = stripped.count("\ufffd") / max(len(stripped), 1)
        if replacement_ratio >= 0.03 or warnings:
            return [{
                "category": "parser_or_format_problem",
                "score": 0.8 if replacement_ratio >= 0.03 else 0.72,
                "threshold": self.config.parser_problem_threshold,
                "title": "Parser or format problem detected",
                "problem_description": "The extracted text contains parsing artifacts or extractor warnings.",
                "why_problematic": "Malformed extraction can lead to poor chunking, incorrect embeddings, or misleading retrieval results.",
                "text_span": {"start": 0, "end": min(len(stripped), 80)},
                "detector": "diagnostics_v1",
            }]
        return []
