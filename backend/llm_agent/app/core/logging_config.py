"""Logging compatibility wrapper for the llm_agent service."""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.append(str(_BACKEND_ROOT))

from shared.logging import ServiceLogger, setup_logging


def get_logger(service_name: str = "llm_agent") -> ServiceLogger:
    """Return a configured shared service logger."""
    return setup_logging(service_name)


__all__ = ["ServiceLogger", "get_logger", "setup_logging"]
