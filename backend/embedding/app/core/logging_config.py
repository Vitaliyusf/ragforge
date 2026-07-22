"""Logging setup for the embedding service."""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.append(str(_BACKEND_ROOT))

from shared.logging import ServiceLogger, setup_logging  # noqa: E402

__all__ = ["ServiceLogger", "setup_logging"]
