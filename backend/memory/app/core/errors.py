"""Memory error compatibility layer backed by shared structured errors."""
import sys
from pathlib import Path

from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.append(str(_BACKEND_ROOT))

from shared.errors import *  # noqa: F401,F403
from shared.errors import coerce_error


def handle_service_error(error: Exception) -> HTTPException:
    """Convert memory-service errors to HTTP exceptions."""
    resolved = coerce_error(error)
    return HTTPException(status_code=resolved.status_code, detail=resolved.message)
