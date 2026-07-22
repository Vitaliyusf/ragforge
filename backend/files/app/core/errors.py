"""Files error compatibility layer backed by shared structured errors."""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.append(str(_BACKEND_ROOT))

from shared.errors import *  # noqa: F401,F403
