"""Metadata extraction service."""
from typing import List, Optional
import json
import re
from collections import Counter

from app.llm.interfaces import ILLMClient, LLMInvocation
from shared.logging import ServiceLogger
from app.core.config import Settings
from app.services.base import BaseService
from app.services.text_window import ContextWindowResolver, estimate_tokens, split_text

KEYWORD_PROMPT = (
    "Extract 10 key words from the following text that would be useful for metadata search "
    "in vector databases and semantic search. Return only a JSON object with a 'keywords' array "
    "containing exactly 10 keywords as strings. Example format: {\"keywords\": [\"keyword1\", \"keyword2\", ...]}."
)

# Keyword extraction only needs a representative sample per section, so sections
# do not overlap — a term dropped at one boundary is near-certain to appear
# elsewhere in the same section.
MAX_KEYWORD_SECTIONS = 8


class MetadataService(BaseService):
    """Service for metadata keyword extraction."""

    def __init__(
        self,
        llm_client: ILLMClient,
        logger: ServiceLogger,
        config: Settings
    ):
        """
        Initialize metadata service.

        Args:
            llm_client: LLM client implementation
            logger: Service logger
            config: Application settings
        """
        self.llm_client = llm_client
        self.logger = logger
        self.config = config
        self.window = ContextWindowResolver(llm_client, config, logger)

    def extract_keywords(
        self,
        text: str,
        model: Optional[str] = None,
        timeout: Optional[float] = None
    ) -> List[str]:
        """
        Extract keywords from text using LLM with fallback to simple extraction.
        
        Args:
            text: Text to extract keywords from
            model: Model name (uses config default if not provided)
            timeout: Request timeout in seconds (uses config default if not provided)
            
        Returns:
            List of 10 keywords
        """
        model = model or self.config.metadata_model
        timeout = timeout or self.config.metadata_timeout
        
        budget = self.window.input_budget_chars(
            model, reserved_tokens=estimate_tokens(KEYWORD_PROMPT)
        )
        sections = split_text(text, budget)
        if len(sections) > MAX_KEYWORD_SECTIONS:
            # Ten keywords do not get better past a point, and each section is a
            # full GPU call. Sample evenly across the document instead of paying
            # for every section or biasing to the opening pages.
            stride = len(sections) / MAX_KEYWORD_SECTIONS
            sections = [sections[int(index * stride)] for index in range(MAX_KEYWORD_SECTIONS)]

        self.logger.log(
            "service:metadata",
            "Extracting keywords",
            {
                "text_length": len(text),
                "model": model,
                "budget_chars": budget,
                "sections": len(sections),
            },
        )

        if len(sections) > 1:
            return self._extract_across_sections(sections, model, timeout, text)

        text = sections[0] if sections else text

        # Calculate timeout - increase for large models (7B+)
        timeout = max(timeout, 120.0)  # At least 2 minutes base timeout
        if "7b" in model.lower() or "13b" in model.lower() or "70b" in model.lower():
            timeout = max(timeout, 300.0)  # At least 5 minutes for large models
            self.logger.log(
                "service:metadata",
                "Using extended timeout for large model",
                {"model": model, "timeout": timeout}
            )
        
        prompt = f"{KEYWORD_PROMPT}\n\n{text}"

        # Try LLM extraction with retry logic
        keywords = None
        max_retries = 1
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    timeout = min(timeout * 1.5, 600.0)  # Cap at 10 minutes
                    self.logger.log(
                        "service:metadata",
                        f"Retrying keyword extraction (attempt {attempt + 1}/{max_retries + 1})",
                        {"model": model, "new_timeout": timeout},
                        hypothesis_id="W"
                    )
                
                llm_response = self.llm_client.generate(
                    LLMInvocation(
                        system_prompt="",
                        raw_prompt=prompt,
                        model=model,
                        timeout=timeout,
                    )
                ).raw_output
                keywords = self._parse_keywords(llm_response)
                
                if keywords and len(keywords) >= 5:  # If we got at least 5 keywords, consider it successful
                    break
            except Exception as gen_error:
                error_str = str(gen_error).lower()
                is_timeout = "timeout" in error_str or "timed out" in error_str
                
                if is_timeout and attempt < max_retries:
                    continue
                else:
                    # Use fallback instead of raising
                    self.logger.log(
                        "service:metadata",
                        f"LLM extraction failed after {attempt + 1} attempts, using fallback",
                        {"model": model, "error": str(gen_error), "is_timeout": is_timeout},
                        hypothesis_id="W"
                    )
                    keywords = None
                    break
        
        # If LLM extraction failed or returned insufficient keywords, use fallback
        if not keywords or len(keywords) < 5:
            self.logger.log(
                "service:metadata",
                "LLM keyword extraction insufficient, using fallback",
                {"llm_keywords_count": len(keywords) if keywords else 0},
                hypothesis_id="W"
            )
            keywords = self._extract_keywords_fallback(text)
        
        # Ensure exactly 10 keywords
        if not keywords:
            keywords = []
        if len(keywords) < 10:
            keywords.extend([""] * (10 - len(keywords)))
        elif len(keywords) > 10:
            keywords = keywords[:10]
        
        self.logger.log(
            "service:metadata",
            "Keywords extracted successfully",
            {"keywords_count": len(keywords)}
        )
        
        return keywords
    
    def _extract_across_sections(
        self,
        sections: List[str],
        model: str,
        timeout: float,
        full_text: str,
    ) -> List[str]:
        """Extract keywords per section and merge them into a single top-10.

        Unlike a summary, keyword lists are merged locally rather than folded
        through the model: ranking by how many sections a term appears in
        favours document-wide terms over ones local to a single section.
        """
        ranked: Counter = Counter()
        for index, section in enumerate(sections):
            try:
                response = self.llm_client.generate(
                    LLMInvocation(
                        system_prompt="",
                        raw_prompt=f"{KEYWORD_PROMPT}\n\n{section}",
                        model=model,
                        timeout=timeout,
                    )
                ).raw_output
            except Exception as gen_error:
                self.logger.log(
                    "service:metadata",
                    "Section keyword extraction failed, skipping section",
                    {"section": index + 1, "of": len(sections), "error": str(gen_error)},
                    hypothesis_id="W",
                )
                continue

            for rank, keyword in enumerate(self._parse_keywords(response)):
                cleaned = keyword.strip()
                if cleaned:
                    # Earlier positions in a section's list weigh slightly more.
                    ranked[cleaned] += max(1, 10 - rank)

        keywords = [keyword for keyword, _ in ranked.most_common(10)]

        if len(keywords) < 5:
            self.logger.log(
                "service:metadata",
                "Section extraction yielded too few keywords, using fallback",
                {"keywords_count": len(keywords)},
                hypothesis_id="W",
            )
            keywords = self._extract_keywords_fallback(full_text)

        keywords = keywords[:10]
        keywords.extend([""] * (10 - len(keywords)))

        self.logger.log(
            "service:metadata",
            "Keywords extracted successfully",
            {"keywords_count": len(keywords), "sections": len(sections)},
        )
        return keywords

    def _parse_keywords(self, llm_response: str) -> List[str]:
        """
        Parse keywords from LLM response.
        
        Args:
            llm_response: Raw LLM response string
            
        Returns:
            List of keyword strings
        """
        try:
            # Try to parse the entire response as JSON
            try:
                data = json.loads(llm_response.strip())
                if isinstance(data, dict) and "keywords" in data:
                    keywords = data["keywords"]
                    if isinstance(keywords, list):
                        return [str(k).strip() for k in keywords if k]
            except json.JSONDecodeError:
                pass
            
            # Try to find JSON object in the response using regex
            json_match = re.search(r'\{[^{}]*"keywords"[^{}]*\[[^\]]*\][^{}]*\}', llm_response, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    if isinstance(data, dict) and "keywords" in data:
                        keywords = data["keywords"]
                        if isinstance(keywords, list):
                            return [str(k).strip() for k in keywords if k]
                except json.JSONDecodeError:
                    pass
            
            # Try to extract array directly
            array_match = re.search(r'\[[^\]]*\]', llm_response)
            if array_match:
                try:
                    keywords = json.loads(array_match.group())
                    if isinstance(keywords, list):
                        return [str(k).strip() for k in keywords if k]
                except json.JSONDecodeError:
                    pass
            
            # Fallback: extract words that look like keywords (quoted, etc.)
            keywords = []
            lines = llm_response.split('\n')
            for line in lines:
                words = re.findall(r'["\']([^"\']+)["\']', line)
                keywords.extend(words)
                if len(keywords) >= 10:
                    break
            
            return keywords[:10] if keywords else []
            
        except Exception as e:
            self.logger.log(
                "service:metadata",
                "Error parsing keywords",
                {"error": str(e), "response": llm_response[:200]},
                hypothesis_id="E"
            )
            return []
    
    def _extract_keywords_fallback(self, text: str) -> List[str]:
        """
        Fallback keyword extraction using simple text analysis.
        
        Args:
            text: Input text to extract keywords from
            
        Returns:
            List of keyword strings (up to 10)
        """
        # Remove common stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
            'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
            'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all', 'each', 'every',
            'other', 'another', 'such', 'only', 'just', 'more', 'most', 'very', 'can', 'cannot'
        }
        
        # Extract words (alphanumeric sequences, at least 3 characters)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        
        # Filter out stop words and count frequencies
        meaningful_words = [w for w in words if w not in stop_words and len(w) > 2]
        word_freq = Counter(meaningful_words)
        
        # Also look for capitalized words (likely proper nouns or important terms)
        capitalized_words = re.findall(r'\b[A-Z][a-z]+\b', text)
        capitalized_freq = Counter([w.lower() for w in capitalized_words if w.lower() not in stop_words])
        
        # Combine frequencies (capitalized words get higher weight)
        combined_freq = word_freq.copy()
        for word, freq in capitalized_freq.items():
            combined_freq[word] = combined_freq.get(word, 0) + freq * 2
        
        # Get top keywords
        top_keywords = [word for word, _ in combined_freq.most_common(10)]
        
        # Pad to 10 if needed
        while len(top_keywords) < 10:
            top_keywords.append("")
        
        return top_keywords[:10]
