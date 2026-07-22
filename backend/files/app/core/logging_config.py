"""Logging compatibility wrapper for the files service."""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.append(str(_BACKEND_ROOT))

from shared.logging import ServiceLogger, setup_logging


def get_logger(name=None):
    """Return the underlying stdlib logger for compatibility call sites."""
    service_name = name or "files"
    return setup_logging(service_name).logger


__all__ = ["ServiceLogger", "get_logger", "setup_logging"]
