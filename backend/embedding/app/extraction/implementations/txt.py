"""TXT file extractor implementation."""
import os

from app.extraction.interfaces import IFileExtractor


class TXTExtractor(IFileExtractor):
    """TXT file text extractor."""
    
    def extract(self, file_path: str, filename: str) -> str:
        """Extract text from TXT file."""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        return text.strip()
    
    def supports(self, filename: str) -> bool:
        """Check if file is a TXT."""
        return os.path.splitext(filename)[1].lower() == '.txt'
