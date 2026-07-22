"""Core exception classes for the llm_agent service."""
from typing import Dict, Any, Optional
from enum import Enum
import traceback


class ErrorCode(Enum):
    """Standard error codes for the application."""
    # General errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    
    # Service errors
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    SERVICE_TIMEOUT = "SERVICE_TIMEOUT"
    SERVICE_ERROR = "SERVICE_ERROR"
    
    # Database errors
    DATABASE_ERROR = "DATABASE_ERROR"
    DATABASE_CONNECTION_ERROR = "DATABASE_CONNECTION_ERROR"
    
    # LLM errors
    LLM_ERROR = "LLM_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_STREAMING_NOT_SUPPORTED = "LLM_STREAMING_NOT_SUPPORTED"


class BaseServiceException(Exception):
    """Base exception for all service exceptions."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        """
        Initialize base service exception.
        
        Args:
            message: Human-readable error message
            error_code: Standard error code
            details: Additional error details
            original_exception: Original exception that caused this error
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.original_exception = original_exception
        self.traceback = traceback.format_exc() if original_exception else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary."""
        return {
            "error": self.message,
            "error_code": self.error_code.value,
            "details": self.details
        }


class ServiceException(BaseServiceException):
    """Exception for service-level errors."""
    pass


class ValidationException(BaseServiceException):
    """Exception for validation errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCode.VALIDATION_ERROR, details, original_exception)


class NotFoundException(BaseServiceException):
    """Exception for not found errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCode.NOT_FOUND, details, original_exception)


class TimeoutException(BaseServiceException):
    """Exception for timeout errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCode.SERVICE_TIMEOUT, details, original_exception)


class StreamingNotSupportedException(BaseServiceException):
    """Exception raised when a provider cannot stream tokens."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        super().__init__(message, ErrorCode.LLM_STREAMING_NOT_SUPPORTED, details, original_exception)
