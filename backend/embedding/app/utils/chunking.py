"""Text chunking utilities for the embedding service.

Strategies (in order of quality):
  paragraph_aware  — split on \\n\\n first, then sentence-aware within each paragraph
  sentence_aware   — split on sentence boundaries
  simple           — fixed-size character chunks
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import List


class IChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        pass


# ---------------------------------------------------------------------------
# Simple character-based strategy
# ---------------------------------------------------------------------------

class SimpleChunkingStrategy(IChunkingStrategy):
    """Fixed-size character chunking with overlap."""

    def chunk(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        if not text:
            return []
        chunks: List[str] = []
        start = 0
        length = len(text)
        while start < length:
            end = min(start + chunk_size, length)
            chunks.append(text[start:end])
            start = end - chunk_overlap
            if start >= length:
                break
        return chunks


# ---------------------------------------------------------------------------
# Sentence-aware strategy
# ---------------------------------------------------------------------------

class SentenceAwareChunkingStrategy(IChunkingStrategy):
    """Keeps sentences intact; falls back to character split for huge sentences."""

    _SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

    def chunk(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        if not text:
            return []
        sentences = self._SENTENCE_SPLIT.split(text)
        chunks: List[str] = []
        current: List[str] = []
        current_size = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            s_len = len(sentence)

            if current_size + s_len + 1 > chunk_size and current:
                chunks.append(" ".join(current))
                overlap = self._get_overlap_text(current, chunk_overlap)
                current = [overlap] if overlap else []
                current_size = len(overlap) if overlap else 0

            if s_len > chunk_size:
                if current:
                    chunks.append(" ".join(current))
                    current, current_size = [], 0
                sub = SimpleChunkingStrategy().chunk(sentence, chunk_size, chunk_overlap)
                chunks.extend(sub[:-1])
                if sub:
                    current = [sub[-1]]
                    current_size = len(sub[-1])
            else:
                current.append(sentence)
                current_size += s_len + 1

        if current:
            chunks.append(" ".join(current))
        return chunks

    @staticmethod
    def _get_overlap_text(sentences: List[str], overlap_size: int) -> str:
        overlap = ""
        for sentence in reversed(sentences):
            if len(overlap) + len(sentence) + 1 <= overlap_size:
                overlap = sentence + (" " + overlap if overlap else "")
            else:
                remaining = overlap_size - len(overlap)
                if remaining > 0:
                    overlap = sentence[-remaining:] + (" " + overlap if overlap else "")
                break
        return overlap


# ---------------------------------------------------------------------------
# Paragraph-aware strategy (best quality)
# ---------------------------------------------------------------------------

class ParagraphAwareChunkingStrategy(IChunkingStrategy):
    """Split on \\n\\n boundaries first, then sentence-aware within each paragraph.

    Algorithm:
    1. Split text into paragraphs on two-or-more blank lines.
    2. Merge adjacent small paragraphs until they would exceed chunk_size.
    3. Apply sentence-aware chunking to any paragraph that is still > chunk_size.
    4. Deduplicate adjacent identical chunks (can occur at overlap boundaries).
    """

    _PARA_SPLIT = re.compile(r"\n{2,}")

    def chunk(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        if not text:
            return []

        raw_paragraphs = [p.strip() for p in self._PARA_SPLIT.split(text) if p.strip()]
        if not raw_paragraphs:
            return []

        sentence_strategy = SentenceAwareChunkingStrategy()
        chunks: List[str] = []
        buffer = ""

        for para in raw_paragraphs:
            if len(para) > chunk_size:
                # Flush buffer first
                if buffer:
                    chunks.append(buffer)
                    # Use last overlap_size chars of buffer as lead-in for continuity
                    buffer = buffer[-chunk_overlap:] if chunk_overlap and len(buffer) > chunk_overlap else ""
                # Sub-chunk the large paragraph
                sub_chunks = sentence_strategy.chunk(para, chunk_size, chunk_overlap)
                if sub_chunks:
                    chunks.extend(sub_chunks[:-1])
                    buffer = sub_chunks[-1]
            elif len(buffer) + len(para) + 2 > chunk_size:
                # Would overflow — flush buffer and start fresh with this paragraph
                if buffer:
                    chunks.append(buffer)
                # Carry overlap from end of buffer into new buffer
                overlap_text = buffer[-chunk_overlap:] if chunk_overlap and len(buffer) > chunk_overlap else ""
                buffer = (overlap_text + "\n\n" + para).strip() if overlap_text else para
            else:
                buffer = (buffer + "\n\n" + para).strip() if buffer else para

        if buffer:
            chunks.append(buffer)

        # Deduplicate exact consecutive duplicates (edge case from overlap logic)
        deduped: List[str] = []
        for c in chunks:
            if not deduped or c != deduped[-1]:
                deduped.append(c)
        return deduped


# ---------------------------------------------------------------------------
# TextChunker — public interface
# ---------------------------------------------------------------------------

_STRATEGY_MAP = {
    "simple": SimpleChunkingStrategy,
    "sentence_aware": SentenceAwareChunkingStrategy,
    "paragraph_aware": ParagraphAwareChunkingStrategy,
}


class TextChunker:
    """Configurable text chunker.

    Args:
        strategy:      One of "paragraph_aware", "sentence_aware", "simple".
        chunk_size:    Max characters per chunk (default 1024).
        chunk_overlap: Overlap between consecutive chunks (default 200).
    """

    def __init__(
        self,
        strategy: str = "paragraph_aware",
        chunk_size: int = 1024,
        chunk_overlap: int = 200,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        cls = _STRATEGY_MAP.get(strategy)
        if cls is None:
            raise ValueError(f"Unknown chunking strategy: {strategy!r}. Choose from {list(_STRATEGY_MAP)}")
        self.strategy: IChunkingStrategy = cls()

    def chunk(self, text: str) -> List[str]:
        return self.strategy.chunk(text, self.chunk_size, self.chunk_overlap)
