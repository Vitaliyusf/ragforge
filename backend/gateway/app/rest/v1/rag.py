"""RAG API routes."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends

from app.core.deps import get_rag_service
from app.core.errors import handle_exception
from app.services.rag_service import RagService
from app.core.auth import get_current_user, require_admin
from shared.auth import AuthIdentity

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/traces/{requested_trace_id}")
async def get_trace(
    requested_trace_id: str,
    _identity: AuthIdentity = Depends(require_admin),
    service: RagService = Depends(get_rag_service),
):
    """Get a RAG trace by requested trace id."""
    try:
        return await service.get_trace(requested_trace_id)
    except Exception as exc:
        raise handle_exception(exc)


@router.post("/feedback")
async def submit_feedback(
    feedback: Dict[str, Any] = Body(...),
    _identity: AuthIdentity = Depends(get_current_user),
    service: RagService = Depends(get_rag_service),
):
    """Submit feedback to the RAG service."""
    try:
        return await service.submit_feedback(feedback)
    except Exception as exc:
        raise handle_exception(exc)
