"""Markdown file extractor — reads .md files as plain UTF-8 text."""
import os

from app.extraction.interfaces import IFileExtractor


class MarkdownExtractor(IFileExtractor):
    """Markdown (.md) file text extractor."""

    def extract(self, file_path: str, filename: str) -> str:
        """Return the raw markdown content as-is.

        Markdown headings (# / ##) act as natural paragraph boundaries which the
        paragraph-aware chunker will respect via double-newline splits.
        """
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def supports(self, filename: str) -> bool:
        return os.path.splitext(filename)[1].lower() == ".md"
