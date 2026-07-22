"""Main router configuration."""
from fastapi import FastAPI

from app.rest.v1 import health
from app.utils.common import setup_cors


def setup_routes(app: FastAPI) -> None:
    """
    Setup all API routes.
    
    Args:
        app: FastAPI application instance
    """
    # Setup CORS
    setup_cors(app)
    
    # Mount v1 routers
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
