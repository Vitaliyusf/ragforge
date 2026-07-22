"""Compatibility config exports for legacy modules."""
from app.core.config import Settings, settings


MemoryConfig = Settings

__all__ = ["MemoryConfig", "Settings", "settings"]
