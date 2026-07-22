"""Main router configuration for the RAG service."""
from fastapi import APIRouter

from app.rest.v1 import rag as rag_v1
from app.rest.v1 import health as health_v1


api_router = APIRouter()

api_router.include_router(rag_v1.router, prefix="/api/v1", tags=["rag"])
api_router.include_router(health_v1.router, tags=["health"])
