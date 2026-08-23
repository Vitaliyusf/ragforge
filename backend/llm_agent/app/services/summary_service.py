"""Summary generation service."""
from typing import Optional
import time

from app.llm.interfaces import ILLMClient, LLMInvocation
from app.core.logging_config import ServiceLogger
from app.core.config import Settings
from app.core.constants import LLMImplementation
from app.core.errors import TimeoutException, ServiceException
from app.services.base import BaseService
from app.services.text_window import ContextWindowResolver, estimate_tokens, split_text

# Instruction for a document that fits the window in one piece. Framed as an
# explicit task because the raw text is otherwise continued as a conversation
# (the model replies to the document instead of summarizing it).
DOCUMENT_PROMPT = (
    "Summarize the following document. Cover all of its main points and keep the "
    "key facts, names, and figures. Write plain prose, no preamble. Do not reply "
    "to the document or add commentary of your own — only summarize it."
)

# Instructions used when a document does not fit the window in one piece.
SECTION_PROMPT = (
    "Summarize this section of a longer document. Keep the key facts, names, and "
    "figures. Write plain prose, no preamble."
)

# Fraction of a section carried into the next one so a sentence spanning a
# boundary is still intelligible somewhere.
SECTION_OVERLAP_RATIO = 0.06


class SummaryService(BaseService):
    """Service for text summarization."""

    def __init__(
        self,
        llm_client: ILLMClient,
        logger: ServiceLogger,
        config: Settings
    ):
        """
        Initialize summary service.

        Args:
            llm_client: LLM client implementation
            logger: Service logger
            config: Application settings
        """
        self.llm_client = llm_client
        self.logger = logger
        self.config = config
        self.window = ContextWindowResolver(llm_client, config, logger)

    @staticmethod
    def _is_mbart_model(model_name: str) -> bool:
        """Check if a model is an mbart (translation) model, not suitable for summarization."""
        if not model_name:
            return False
        return "mbart" in model_name.lower()
    
    def generate_summary(
        self,
        text: str,
        model: Optional[str] = None,
        prompt_prefix: str = "TL;DR",
        timeout: Optional[float] = None
    ) -> str:
        """
        Generate a summary of the given text.
        
        Args:
            text: Text to summarize
            model: Model name (uses config default if not provided)
            prompt_prefix: Prompt prefix for summarization
            timeout: Request timeout in seconds (uses config default if not provided)
            
        Returns:
            Generated summary
            
        Raises:
            TimeoutException: If generation times out
            ServiceException: If generation fails
        """
        model = model or self.config.summary_model
        
        # Validate model: mbart models are translation models, not suitable for summarization
        if self._is_mbart_model(model):
            error_msg = f"Model {model} is a translation model (mbart), not suitable for summarization."
            self.logger.log(
                "service:summary",
                "Invalid model for summarization",
                {"model": model, "error": error_msg},
                hypothesis_id="E"
            )
            # Fallback to default summary model
            model = "facebook/bart-large-cnn"
            self.logger.log(
                "service:summary",
                "Using fallback summary model",
                {"fallback_model": model}
            )
        
        timeout = timeout or self.config.summary_timeout
        
        # Calculate timeout - increase for large models (7B+)
        if "7b" in model.lower() or "13b" in model.lower() or "70b" in model.lower():
            timeout = max(timeout, 240.0)  # At least 4 minutes for large models
            self.logger.log(
                "service:summary",
                "Using extended timeout for large model",
                {"model": model, "timeout": timeout}
            )
        
        # A caller-supplied prompt overrides the default; the legacy "TL;DR"
        # sentinel is treated as "use the standard summarization instruction",
        # which the small model follows far better than a bare "TL;DR".
        instruction = DOCUMENT_PROMPT if prompt_prefix in ("", "TL;DR") else prompt_prefix
        max_tokens = self.config.summary_max_tokens

        budget = self._budget_chars(model, instruction, max_tokens)
        sections = split_text(text, budget, int(budget * SECTION_OVERLAP_RATIO))

        self.logger.log(
            "service:summary",
            "Generating summary",
            {
                "text_length": len(text),
                "model": model,
                "timeout": timeout,
                "budget_chars": budget,
                "sections": len(sections),
                "max_tokens": max_tokens,
            }
        )

        if len(sections) <= 1:
            summary = self._generate_with_retry(
                f"{instruction}\n\n{text}", model, timeout, max_tokens
            )
        else:
            summary = self._summarize_sections(sections, model, timeout, max_tokens)

        if not summary or len(summary.strip()) <= 10:
            raise ServiceException("Generated summary is too short or empty")

        self.logger.log(
            "service:summary",
            "Summary generated successfully",
            {"summary_length": len(summary)}
        )

        return summary

    def _budget_chars(self, model: str, instruction: str, max_tokens: int) -> int:
        """Characters of source text that fit in one call for this model.

        Reserves ``max_tokens`` for the response so that a section plus its
        (now much larger) summary still fit inside the context window.
        """
        # Reserve room for whichever instruction block is longest, so the same
        # budget is safe for the single-shot and per-section prompts alike.
        overhead = max(
            estimate_tokens(instruction),
            estimate_tokens(SECTION_PROMPT),
        )
        budget = self.window.input_budget_chars(
            model, reserved_tokens=overhead, output_tokens=max_tokens
        )

        # Ollama has no reliable window probe; keep the historical conservative cap.
        if self.config.llm_implementation == LLMImplementation.OLLAMA:
            budget = min(budget, 3000)
        return budget

    def _summarize_sections(
        self, sections: list, model: str, timeout: float, max_tokens: int
    ) -> str:
        """Summarize each section, then join the pieces into one summary.

        The per-section summaries are concatenated as continuous prose rather
        than folded through a single combine pass. A combine pass would re-squeeze
        the whole document back into one ``vllm_max_tokens``-capped response,
        truncating long documents; concatenation lets the summary length grow
        with the document so nothing is dropped.
        """
        partials = []
        for index, section in enumerate(sections):
            self.logger.log(
                "service:summary",
                "Summarizing section",
                {"section": index + 1, "of": len(sections), "chars": len(section)},
            )
            partials.append(
                self._generate_with_retry(
                    f"{SECTION_PROMPT}\n\n{section}", model, timeout, max_tokens
                )
            )

        return "\n\n".join(part for part in partials if part)

    def _generate_with_retry(
        self, full_prompt: str, model: str, timeout: float, max_tokens: Optional[int] = None
    ) -> str:
        """Run one generation, retrying once on a fallback model."""
        summary = None
        max_retries = 1
        fallback_model = "facebook/bart-large-cnn" if model != "facebook/bart-large-cnn" else None
        
        for attempt in range(max_retries + 1):
            try:
                current_model = fallback_model if (attempt > 0 and fallback_model) else model
                
                if attempt > 0:
                    self.logger.log(
                        "service:summary",
                        f"Retrying with fallback model (attempt {attempt + 1}/{max_retries + 1})",
                        {"fallback_model": current_model},
                        hypothesis_id="W"
                    )
                    # Increase timeout for retry
                    timeout = timeout * 1.5
                
                summary = self.llm_client.generate(
                    LLMInvocation(
                        system_prompt="",
                        raw_prompt=full_prompt,
                        model=current_model,
                        timeout=timeout,
                        max_tokens=max_tokens,
                    )
                ).raw_output
                
                if summary and len(summary.strip()) > 10:  # Ensure we got a meaningful summary
                    if attempt > 0:
                        self.logger.log(
                            "service:summary",
                            "Summary generated successfully with fallback model",
                            {"fallback_model": current_model, "summary_length": len(summary)}
                        )
                    break
            except Exception as gen_error:
                error_str = str(gen_error)
                is_timeout = "timeout" in error_str.lower() or "timed out" in error_str.lower()
                is_model_error = "failed to load" in error_str.lower() or "unknown task" in error_str.lower()
                is_connection_error = "cannot connect" in error_str.lower() or "connection" in error_str.lower()
                
                if attempt < max_retries:
                    # For connection errors, wait and retry
                    if is_connection_error:
                        wait_time = 5.0 * (attempt + 1)
                        time.sleep(wait_time)
                        continue
                    # Retry with fallback model if available
                    elif fallback_model and (is_model_error or is_timeout):
                        continue
                else:
                    # Last attempt failed
                    if is_timeout:
                        raise TimeoutException(f"Summary generation timed out after {timeout:.1f}s", original_exception=gen_error)
                    elif is_model_error:
                        raise ServiceException(f"Model error: {error_str[:200]}", original_exception=gen_error)
                    else:
                        raise ServiceException(f"Error generating summary: {error_str[:200]}", original_exception=gen_error)

        if not summary or len(summary.strip()) <= 10:
            raise ServiceException("Generated summary is too short or empty")

        return summary
