"""Prompt-injection scoring helpers used by gateway chat handling.

This module applies regex, structural, encoding, and length heuristics to a
single input string and returns a `PromptGuardResult`. It scores suspicious
patterns but does not raise exceptions on its own; callers decide whether to
flag or block based on the configured thresholds.
"""
import re
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("prompt_guard")


@dataclass
class PromptGuardResult:
    """Outcome returned by `PromptGuard.check`.

    Attributes:
        safe: `True` when the computed score is below `block_threshold`.
        risk_score: Rounded score between `0.0` and `1.0`.
        flags: Machine-readable detection flags for matched heuristics.
        sanitized_input: Original text truncated to the configured max length.
    """
    safe: bool
    risk_score: float  # 0.0 (safe) to 1.0 (dangerous)
    flags: List[str] = field(default_factory=list)
    sanitized_input: str = ""


class PromptGuard:
    """
    Score one user-provided prompt for injection indicators.

    The current implementation adds heuristic scores from six detection layers:
    known phrases, role switching, delimiter abuse, encoding tricks, line or
    size excess, and unusually high special-character density. The caller can
    use `flag_threshold` for logging or soft handling and `block_threshold` for
    hard rejection.
    """

    # ── Known injection patterns ────────────────────────────────
    INJECTION_PATTERNS = [
        (r"ignore\s+(all\s+)?previous\s+(instructions|prompts|rules)", 0.4, "injection:ignore_previous"),
        (r"disregard\s+(all\s+)?previous", 0.4, "injection:disregard"),
        (r"forget\s+(everything|all|your)\s*(instructions|rules|training)?", 0.35, "injection:forget"),
        (r"you\s+are\s+now\s+", 0.35, "injection:role_override"),
        (r"act\s+as\s+(if\s+you\s+are|a)\s+", 0.2, "injection:act_as"),
        (r"pretend\s+(you\s+are|to\s+be)", 0.3, "injection:pretend"),
        (r"new\s+instructions?\s*:", 0.35, "injection:new_instructions"),
        (r"system\s*prompt\s*:", 0.4, "injection:system_prompt_leak"),
        (r"```\s*system", 0.4, "injection:code_block_system"),
        (r"<\s*system\s*>", 0.4, "injection:xml_system_tag"),
        (r"reveal\s+(your|the)\s+(system|original|initial)\s*(prompt|instructions)", 0.45, "injection:reveal_prompt"),
        (r"what\s+(are|is)\s+your\s+(system|original)\s*(prompt|instructions)", 0.3, "injection:query_prompt"),
        (r"output\s+your\s+(initial|system|original)\s*prompt", 0.45, "injection:output_prompt"),
        (r"repeat\s+(the\s+)?(text|words|instructions)\s+above", 0.35, "injection:repeat_above"),
        (r"do\s+anything\s+now", 0.3, "injection:dan_jailbreak"),
        (r"jailbreak", 0.4, "injection:jailbreak_keyword"),
    ]

    # ── Role-switching markers ──────────────────────────────────
    ROLE_SWITCH_PATTERNS = [
        (r"^(assistant|system|ai|bot)\s*:", 0.35, "structure:role_switch"),
        (r"\n(assistant|system|ai)\s*:", 0.3, "structure:inline_role_switch"),
    ]

    # ── Delimiter injection ─────────────────────────────────────
    DELIMITER_PATTERNS = [
        (r"#{3,}", 0.15, "structure:hash_delimiter"),
        (r"-{3,}", 0.1, "structure:dash_delimiter"),
        (r"`{3,}", 0.15, "structure:backtick_delimiter"),
        (r"\[INST\]", 0.35, "structure:instruction_tag"),
        (r"<\|im_start\|>", 0.4, "structure:chatml_tag"),
        (r"<\|endoftext\|>", 0.4, "structure:eos_token"),
    ]

    def __init__(
        self,
        flag_threshold: float = 0.6,
        block_threshold: float = 0.8,
        max_input_length: int = 4096,
        max_line_count: int = 50,
    ):
        self.flag_threshold = flag_threshold
        self.block_threshold = block_threshold
        self.max_input_length = max_input_length
        self.max_line_count = max_line_count

        # Pre-compile all patterns
        self._injection_patterns = [
            (re.compile(p, re.IGNORECASE | re.MULTILINE), score, flag)
            for p, score, flag in self.INJECTION_PATTERNS
        ]
        self._role_patterns = [
            (re.compile(p, re.IGNORECASE | re.MULTILINE), score, flag)
            for p, score, flag in self.ROLE_SWITCH_PATTERNS
        ]
        self._delimiter_patterns = [
            (re.compile(p, re.MULTILINE), score, flag)
            for p, score, flag in self.DELIMITER_PATTERNS
        ]

        # Metrics
        self._total_checked = 0
        self._total_flagged = 0
        self._total_blocked = 0

    def check(self, text: str) -> PromptGuardResult:
        """
        Analyze one input string and return the current heuristic assessment.

        Args:
            text: User-supplied prompt text. Empty strings are allowed.

        Returns:
            PromptGuardResult containing the rounded score, accumulated flags,
            and a max-length-truncated copy of the input.

        Side effects:
            Updates in-memory metrics counters and logs flagged or blocked
            inputs when thresholds are crossed.
        """
        self._total_checked += 1
        flags = []
        risk_score = 0.0

        # Layer 1: Length and complexity checks
        if len(text) > self.max_input_length:
            flags.append(f"length:exceeds_max({len(text)}/{self.max_input_length})")
            risk_score += 0.1

        line_count = text.count("\n") + 1
        if line_count > self.max_line_count:
            flags.append(f"length:too_many_lines({line_count}/{self.max_line_count})")
            risk_score += 0.1

        # Layer 2: Known injection patterns
        for pattern, score, flag in self._injection_patterns:
            if pattern.search(text):
                flags.append(flag)
                risk_score += score

        # Layer 3: Role-switching detection
        for pattern, score, flag in self._role_patterns:
            if pattern.search(text):
                flags.append(flag)
                risk_score += score

        # Layer 4: Delimiter injection
        for pattern, score, flag in self._delimiter_patterns:
            if pattern.search(text):
                flags.append(flag)
                risk_score += score

        # Layer 5: Encoding-based attacks
        encoding_flags, encoding_score = self._check_encoding_attacks(text)
        flags.extend(encoding_flags)
        risk_score += encoding_score

        # Layer 6: Excessive special characters (potential obfuscation)
        special_ratio = sum(1 for c in text if not c.isalnum() and not c.isspace()) / max(1, len(text))
        if special_ratio > 0.4:
            flags.append(f"encoding:high_special_char_ratio({special_ratio:.2f})")
            risk_score += 0.15

        # Cap risk score at 1.0
        risk_score = min(1.0, risk_score)

        # Determine safety
        safe = risk_score < self.block_threshold

        if risk_score >= self.block_threshold:
            self._total_blocked += 1
            logger.warning(
                f"Prompt BLOCKED: risk_score={risk_score:.2f}, flags={flags}, "
                f"text_preview={text[:100]!r}"
            )
        elif risk_score >= self.flag_threshold:
            self._total_flagged += 1
            logger.info(
                f"Prompt FLAGGED: risk_score={risk_score:.2f}, flags={flags}"
            )

        # Sanitize: truncate to max length
        sanitized = text[:self.max_input_length] if len(text) > self.max_input_length else text

        return PromptGuardResult(
            safe=safe,
            risk_score=round(risk_score, 3),
            flags=flags,
            sanitized_input=sanitized,
        )

    def _check_encoding_attacks(self, text: str) -> tuple:
        """Inspect one string for encoding-based bypass attempts.

        Args:
            text: Input string to inspect.

        Returns:
            A `(flags, score)` tuple where `flags` is a list of machine-readable
            markers and `score` is the incremental heuristic risk.
        """
        flags = []
        score = 0.0

        # Base64 encoded payloads (look for base64 strings > 20 chars)
        b64_pattern = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")
        b64_matches = b64_pattern.findall(text)
        for match in b64_matches:
            try:
                decoded = base64.b64decode(match).decode("utf-8", errors="ignore").lower()
                # Check if decoded content contains injection keywords
                danger_keywords = ["ignore", "system", "prompt", "instructions", "jailbreak"]
                if any(kw in decoded for kw in danger_keywords):
                    flags.append("encoding:base64_injection")
                    score += 0.4
                    break
            except Exception:
                pass

        # Unicode escape sequences (\uXXXX)
        unicode_escapes = re.findall(r"\\u[0-9a-fA-F]{4}", text)
        if len(unicode_escapes) > 5:
            flags.append(f"encoding:unicode_escapes({len(unicode_escapes)})")
            score += 0.2

        # HTML entities
        html_entities = re.findall(r"&#?\w+;", text)
        if len(html_entities) > 3:
            flags.append(f"encoding:html_entities({len(html_entities)})")
            score += 0.15

        # Zero-width characters (potential homoglyph attack)
        zwc_count = sum(1 for c in text if ord(c) in (0x200B, 0x200C, 0x200D, 0xFEFF, 0x00AD))
        if zwc_count > 0:
            flags.append(f"encoding:zero_width_chars({zwc_count})")
            score += 0.25

        return flags, score

    @property
    def metrics(self) -> Dict[str, Any]:
        """Return in-memory counters for basic guard monitoring."""
        return {
            "total_checked": self._total_checked,
            "total_flagged": self._total_flagged,
            "total_blocked": self._total_blocked,
            "block_rate": self._total_blocked / max(1, self._total_checked),
        }
