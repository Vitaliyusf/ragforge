"""LLM client interfaces and invocation contracts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


TokenCallback = Callable[[str, int], None]


class ProviderProtocolError(RuntimeError):
    """The provider rejected or violated the requested API protocol."""


class ProviderHTTPError(RuntimeError):
    """The provider failed at the HTTP boundary."""


class ProviderTimeoutError(RuntimeError):
    """The provider request exceeded its deadline."""


class ProviderOverloadedError(RuntimeError):
    """The provider could not admit work within its bounded wait."""


@dataclass
class LLMUsage:
    """Normalized token usage metadata returned by providers."""

    provider: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize usage information into a plain dictionary."""
        return {
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class LLMInvocation:
    """Normalized invocation payload passed from the service to a provider."""

    system_prompt: str
    raw_prompt: str
    model: str
    timeout: float = 60.0
    on_token: Optional[TokenCallback] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Per-call output-token cap. When None the provider falls back to its
    # configured default. Summarization raises this so long summaries are not
    # truncated mid-sentence at the small chat default.
    max_tokens: Optional[int] = None

    @property
    def streaming(self) -> bool:
        """Return True when the caller requested incremental token delivery."""
        return self.on_token is not None

    def to_prompt(self) -> str:
        """Render a single prompt string for providers that accept plain text."""
        if self.system_prompt:
            return f"System:\n{self.system_prompt}\n\nUser:\n{self.raw_prompt}"
        return self.raw_prompt


@dataclass
class LLMGenerationResult:
    """Normalized provider response returned to the execution service."""

    raw_output: str
    usage: LLMUsage
    finish_reason: str = "completed"


class ILLMClient(ABC):
    """Interface for LLM clients."""

    @abstractmethod
    def generate(self, invocation: LLMInvocation) -> LLMGenerationResult:
        """
        Generate text from a normalized invocation.

        Args:
            invocation: Rendered prompt payload and provider execution options.

        Returns:
            Normalized provider result.

        Raises:
            Exception: If generation fails.
        """
        raise NotImplementedError

    @abstractmethod
    def list_models(self) -> list:
        """
        List available models.

        Returns:
            List of model names.
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM service is available."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Close process-owned provider resources when the implementation has any."""
