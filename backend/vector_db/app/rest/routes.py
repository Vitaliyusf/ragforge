"""Main routes configuration."""
from fastapi import APIRouter

from app.rest.v1 import health, vectors

api_router = APIRouter()

api_router.include_router(health.router, prefix="/v1", tags=["health"])
api_router.include_router(vectors.router, prefix="/v1", tags=["vectors"])
