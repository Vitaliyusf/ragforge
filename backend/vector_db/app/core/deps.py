"""Dependency injection getters for FastAPI Depends().

All getters use deferred imports from app.main to avoid circular
imports while still returning the shared singletons.
"""
from app.services.vector_service import VectorService


def get_vector_service() -> VectorService:
    """Return the shared VectorService singleton initialised in lifespan."""
    from app.main import _vector_service  # deferred — avoids circular import

    if _vector_service is None:
        raise RuntimeError("VectorService not initialised — lifespan not complete")
    return _vector_service
