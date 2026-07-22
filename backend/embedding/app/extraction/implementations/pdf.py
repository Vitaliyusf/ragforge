"""PDF file extractor — uses pymupdf (fitz) for accurate text extraction.

pymupdf handles multi-column layouts, tables, and complex formatting far better
than PyPDF2.  Text is extracted page by page and joined with paragraph breaks so
that the downstream paragraph-aware chunker can split on natural boundaries.
"""
import os

try:
    import fitz  # pymupdf
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    fitz = None

from app.extraction.interfaces import IFileExtractor


class PDFExtractor(IFileExtractor):
    """PDF text extractor backed by pymupdf (fitz)."""

    def __init__(self) -> None:
        if not HAS_FITZ:
            raise ImportError("pymupdf is required for PDF extraction.  Install with: pip install pymupdf")

    def extract(self, file_path: str, filename: str) -> str:
        """Extract text from all pages, preserving paragraph structure.

        Each page's text is appended with a double-newline so the
        paragraph-aware chunker can detect page boundaries as natural split points.
        """
        if not HAS_FITZ:
            raise ImportError("pymupdf is required for PDF extraction")

        pages: list[str] = []
        with fitz.open(file_path) as doc:
            for page in doc:
                # "text" mode preserves whitespace and paragraph breaks
                page_text = page.get_text("text").strip()
                if page_text:
                    pages.append(page_text)

        return "\n\n".join(pages)

    def supports(self, filename: str) -> bool:
        return os.path.splitext(filename)[1].lower() == ".pdf"
