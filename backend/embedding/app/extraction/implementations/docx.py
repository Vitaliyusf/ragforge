"""DOCX file extractor implementation."""
import os

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    Document = None

from app.extraction.interfaces import IFileExtractor


class DOCXExtractor(IFileExtractor):
    """DOCX file text extractor."""
    
    def __init__(self):
        """Initialize DOCX extractor."""
        if not HAS_DOCX:
            raise ImportError("python-docx is required for DOCX extraction")
    
    def extract(self, file_path: str, filename: str) -> str:
        """Extract text from DOCX file."""
        if not HAS_DOCX:
            raise ImportError("python-docx is required for DOCX extraction")
        
        doc = Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    
    def supports(self, filename: str) -> bool:
        """Check if file is a DOCX."""
        return os.path.splitext(filename)[1].lower() == '.docx'
