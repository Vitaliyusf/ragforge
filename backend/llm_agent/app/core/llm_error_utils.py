"""Utility functions for detecting LLM unavailable errors."""
import httpx


def is_llm_unavailable_error(exception: Exception) -> bool:
    """
    Check if an exception indicates that the LLM service is unavailable.
    
    This function detects various error types that indicate LLM unavailability:
    - HTTP 404 errors (endpoint not found, model not loaded)
    - Connection errors (service not reachable)
    - RuntimeError messages indicating service is not available/ready
    - ServiceException wrapping unavailable errors
    
    Args:
        exception: The exception to check
        
    Returns:
        True if the exception indicates LLM is unavailable, False otherwise
    """
    # Check for HTTP 404 errors
    if isinstance(exception, httpx.HTTPStatusError):
        if exception.response.status_code == 404:
            return True
    
    # Check for connection errors
    if isinstance(exception, (httpx.ConnectError, ConnectionError)):
        return True
    
    # Check error message for indicators of unavailability
    error_message = str(exception).lower()
    unavailable_indicators = [
        "404",
        "not available",
        "not ready",
        "cannot connect",
        "connection refused",
        "connection error",
        "service is not available",
        "model is not ready",
        "endpoint not found",
        "unable to connect"
    ]
    
    for indicator in unavailable_indicators:
        if indicator in error_message:
            return True
    
    # Check if it's a ServiceException with unavailable error code
    # (in case it wraps an unavailable error)
    if hasattr(exception, 'error_code'):
        if hasattr(exception.error_code, 'value'):
            if exception.error_code.value == "LLM_UNAVAILABLE":
                return True
    
    # Check original exception if wrapped
    if hasattr(exception, 'original_exception') and exception.original_exception:
        return is_llm_unavailable_error(exception.original_exception)
    
    return False
