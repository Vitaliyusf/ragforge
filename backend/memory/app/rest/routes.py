"""Main routes configuration."""
from fastapi import APIRouter

from app.rest.v1 import memory


api_router = APIRouter()
api_router.include_router(memory.router, prefix="/v1", tags=["memory"])
