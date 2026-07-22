"""Main router configuration."""
from fastapi import APIRouter

from app.rest.v1 import files as files_v1
from app.rest.v1 import health as health_v1

api_router = APIRouter()

api_router.include_router(files_v1.router, prefix="/v1", tags=["files"])
api_router.include_router(health_v1.router, prefix="/v1", tags=["health"])
