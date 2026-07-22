"""Output guard for post-generation safety checks.

Analyzes LLM responses for leaked system prompts, PII, hallucinated URLs,
and other potentially harmful content before returning to the user.

Usage:
    from shared.output_guard import OutputGuard

    guard = OutputGuard()
    result = guard.check(llm_response, system_prompt_fragments=["You are a helpful assistant"])
    if result.flags:
        response["output_guard_flags"] = result.flags
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("output_guard")


@dataclass
class OutputGuardResult:
    """Result of an output guard check."""
    safe: bool
    risk_score: float
    flags: List[str] = field(default_factory=list)
    redacted_output: Optional[str] = None


class OutputGuard:
    """
    Post-generation safety checker for LLM outputs.

    Detection layers:
    1. System prompt leakage — detects fragments of the system prompt in output
    2. PII detection — emails, phone numbers, SSNs, credit cards
    3. Hallucinated URLs — detects fabricated URLs/links
    4. Harmful content indicators — detects code injection attempts in output
    """

    # PII patterns
    PII_PATTERNS = [
        (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "pii:email"),
        (re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"), "pii:ssn"),
        (re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"), "pii:credit_card"),
        (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "pii:phone"),
    ]

    # URL patterns (detect potentially hallucinated links)
    URL_PATTERN = re.compile(
        r"https?://[^\s<>\"')\]]+",
        re.IGNORECASE,
    )

    # Known safe URL domains (not hallucinated)
    SAFE_DOMAINS = {
        "github.com", "stackoverflow.com", "python.org", "docs.python.org",
        "wikipedia.org", "en.wikipedia.org", "google.com", "mozilla.org",
        "developer.mozilla.org", "w3.org", "ietf.org", "rfc-editor.org",
    }

    def __init__(
        self,
        system_prompt_fragments: Optional[List[str]] = None,
        block_threshold: float = 0.7,
    ):
        self.system_prompt_fragments = system_prompt_fragments or []
        self.block_threshold = block_threshold

        self._total_checked = 0
        self._total_flagged = 0

    def check(
        self,
        output: str,
        system_prompt_fragments: Optional[List[str]] = None,
    ) -> OutputGuardResult:
        """
        Analyze LLM output for safety issues.

        Args:
            output: The LLM-generated response text
            system_prompt_fragments: Optional override for system prompt detection

        Returns:
            OutputGuardResult with assessment
        """
        self._total_checked += 1
        flags = []
        risk_score = 0.0
        fragments = system_prompt_fragments or self.system_prompt_fragments

        # Layer 1: System prompt leakage
        leaked = self._check_system_prompt_leak(output, fragments)
        flags.extend(leaked)
        risk_score += len(leaked) * 0.3

        # Layer 2: PII detection
        pii_flags = self._check_pii(output)
        flags.extend(pii_flags)
        risk_score += len(pii_flags) * 0.2

        # Layer 3: Hallucinated URLs
        url_flags = self._check_urls(output)
        flags.extend(url_flags)
        risk_score += len(url_flags) * 0.1

        # Layer 4: Code injection in output
        code_flags = self._check_code_injection(output)
        flags.extend(code_flags)
        risk_score += len(code_flags) * 0.25

        risk_score = min(1.0, risk_score)
        safe = risk_score < self.block_threshold

        if flags:
            self._total_flagged += 1
            logger.info(
                f"Output flagged: risk_score={risk_score:.2f}, flags={flags}, "
                f"output_preview={output[:100]!r}"
            )

        return OutputGuardResult(
            safe=safe,
            risk_score=round(risk_score, 3),
            flags=flags,
        )

    def _check_system_prompt_leak(self, output: str, fragments: List[str]) -> List[str]:
        """Check if the output contains system prompt fragments."""
        flags = []
        output_lower = output.lower()

        for fragment in fragments:
            if len(fragment) < 10:
                continue  # Skip very short fragments (high false positive rate)
            if fragment.lower() in output_lower:
                flags.append("leak:system_prompt_fragment")
                break  # One detection is enough

        return flags

    def _check_pii(self, output: str) -> List[str]:
        """Check for PII patterns in the output."""
        flags = []
        for pattern, flag_name in self.PII_PATTERNS:
            if pattern.search(output):
                flags.append(flag_name)
        return flags

    def _check_urls(self, output: str) -> List[str]:
        """Check for potentially hallucinated URLs."""
        flags = []
        urls = self.URL_PATTERN.findall(output)

        for url in urls:
            # Extract domain
            domain_match = re.search(r"https?://([^/\s]+)", url)
            if domain_match:
                domain = domain_match.group(1).lower()
                # Remove port number if present
                domain = domain.split(":")[0]
                if domain not in self.SAFE_DOMAINS and not domain.endswith(".gov"):
                    flags.append(f"url:potentially_hallucinated({domain})")

        return flags

    def _check_code_injection(self, output: str) -> List[str]:
        """Check for code injection patterns in output."""
        flags = []
        danger_patterns = [
            (r"<script[^>]*>", "code:script_tag"),
            (r"javascript:", "code:javascript_uri"),
            (r"on\w+\s*=\s*[\"']", "code:event_handler"),
            (r"eval\s*\(", "code:eval"),
            (r"exec\s*\(", "code:exec"),
        ]
        for pattern, flag in danger_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                flags.append(flag)
        return flags

    @property
    def metrics(self) -> Dict[str, Any]:
        """Output guard metrics."""
        return {
            "total_checked": self._total_checked,
            "total_flagged": self._total_flagged,
            "flag_rate": self._total_flagged / max(1, self._total_checked),
        }
