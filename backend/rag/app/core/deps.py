"""Dependency injection getters for FastAPI Depends() usage in the rag service.

All DI getters live here.  Route files import from this module exclusively.
main.py owns the singleton variables; getters use deferred imports to avoid
circular imports at module load time.
"""
from __future__ import annotations


def get_rag_service():
    """Return the runtime RAGService singleton."""
    from app.main import rag_service  # deferred — avoids circular import
    if rag_service is None:
        raise RuntimeError("RAGService not initialised")
    return rag_service


def get_websocket_service():
    """Return the runtime WebSocketService singleton."""
    from app.main import websocket_service  # deferred — avoids circular import
    if websocket_service is None:
        raise RuntimeError("WebSocketService not initialised")
    return websocket_service
