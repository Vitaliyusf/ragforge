"""Factory for creating file extractors."""
from typing import List, Optional

from app.extraction.interfaces import IFileExtractor
from app.extraction.implementations.pdf import PDFExtractor
from app.extraction.implementations.docx import DOCXExtractor
from app.extraction.implementations.doc import DOCExtractor
from app.extraction.implementations.txt import TXTExtractor
from app.extraction.implementations.md import MarkdownExtractor


class FileExtractorFactory:
    """Factory for creating file extractor instances."""
    
    @staticmethod
    def create_all() -> List[IFileExtractor]:
        """
        Create all available file extractors.
        
        Returns:
            List of extractor instances (only those that can be instantiated)
        """
        extractors = []
        
        # Try to create each extractor
        for extractor_class in [PDFExtractor, DOCXExtractor, DOCExtractor, TXTExtractor, MarkdownExtractor]:
            try:
                extractors.append(extractor_class())
            except ImportError:
                # Library not available, skip this extractor
                pass
        
        return extractors
    
    @staticmethod
    def get_extractor_for_file(extractors: List[IFileExtractor], filename: str) -> Optional[IFileExtractor]:
        """
        Get the appropriate extractor for a file.
        
        Args:
            extractors: List of available extractors
            filename: Name of the file
            
        Returns:
            Extractor instance or None if no extractor supports the file
        """
        for extractor in extractors:
            if extractor.supports(filename):
                return extractor
        return None
