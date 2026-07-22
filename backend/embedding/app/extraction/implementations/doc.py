"""DOC file extractor implementation."""
import os

try:
    import docx2txt
    HAS_DOCX2TXT = True
except ImportError:
    HAS_DOCX2TXT = False
    docx2txt = None

from app.extraction.interfaces import IFileExtractor


class DOCExtractor(IFileExtractor):
    """DOC file text extractor."""
    
    def __init__(self):
        """Initialize DOC extractor."""
        if not HAS_DOCX2TXT:
            raise ImportError("docx2txt is required for DOC extraction")
    
    def extract(self, file_path: str, filename: str) -> str:
        """Extract text from DOC file."""
        if not HAS_DOCX2TXT:
            raise ImportError("docx2txt is required for DOC extraction")
        
        text = docx2txt.process(file_path)
        return text.strip()
    
    def supports(self, filename: str) -> bool:
        """Check if file is a DOC."""
        return os.path.splitext(filename)[1].lower() == '.doc'
