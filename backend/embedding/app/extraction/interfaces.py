"""File extraction interfaces."""
from abc import ABC, abstractmethod


class IFileExtractor(ABC):
    """Interface for file text extraction."""
    
    @abstractmethod
    def extract(self, file_path: str, filename: str) -> str:
        """
        Extract text from a file.
        
        Args:
            file_path: Path to the file
            filename: Name of the file (for type detection)
            
        Returns:
            Extracted text
            
        Raises:
            ValueError: If file type is not supported
            ImportError: If required library is not available
            FileNotFoundError: If file does not exist
        """
        pass
    
    @abstractmethod
    def supports(self, filename: str) -> bool:
        """
        Check if the extractor supports the file type.
        
        Args:
            filename: Name of the file
            
        Returns:
            True if the file type is supported
        """
        pass
