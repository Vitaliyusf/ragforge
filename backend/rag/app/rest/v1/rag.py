"""Secondary HTTP query interface for the active `rag` runtime."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_rag_service
from shared.errors import ServiceException
from app.schemas.rag import RAGRequest, RAGResponse
from app.services.rag_service import RAGService
from shared.http_auth import require_internal_identity
from shared.auth import AuthIdentity

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/query", response_model=RAGResponse)
async def query_rag(
    request: RAGRequest,
    _identity: AuthIdentity = Depends(require_internal_identity),
    rag_service: RAGService = Depends(get_rag_service),
) -> RAGResponse:
    """Process a secondary HTTP query through the same conversation runtime."""
    try:
        result = await rag_service.query(
            question=request.question,
            model=request.model,
            mode=request.mode,
            answer_mode=request.answer_mode or "quick",
        )
        return RAGResponse(**result)
    except ServiceException:
        logger.exception("RAG query failed because a downstream service is unavailable")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    except Exception:
        logger.exception("Unexpected RAG query failure")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
