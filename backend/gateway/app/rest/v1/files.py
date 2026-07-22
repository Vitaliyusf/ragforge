"""File API routes."""
from fastapi import APIRouter, Depends, UploadFile, File, Query

from app.core.deps import get_auth_service, get_file_service
from app.core.errors import handle_exception, RPCConnectionError, RPCTimeoutError
from app.schemas.file import ReviewDecisionRequest
from app.services.file_service import FileService
from app.core.auth import get_current_user, require_admin
from shared.auth import AuthIdentity
from app.services.auth_service import AuthService

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    _identity: AuthIdentity = Depends(get_current_user),
    service: FileService = Depends(get_file_service)
):
    """File upload endpoint."""
    try:
        return await service.upload_file(file)
    except Exception as e:
        raise handle_exception(e)


@router.get("/suggested-questions")
async def get_suggested_questions(
    _identity: AuthIdentity = Depends(get_current_user),
    service: FileService = Depends(get_file_service)
):
    """Get suggested questions from complete files for Start Conversation page.

    Returns an empty list when RabbitMQ is unavailable so the frontend can
    fall back to default prompts without a console error.
    """
    try:
        return await service.get_suggested_questions()
    except (RPCConnectionError, RPCTimeoutError):
        return {"suggested_questions": []}
    except Exception as e:
        raise handle_exception(e)


@router.get("/mine")
async def get_own_files(
    _identity: AuthIdentity = Depends(get_current_user),
    service: FileService = Depends(get_file_service)
):
    """List the calling user's own uploads.

    Ownership scoping happens in the files service repository, and the reply is
    already narrowed to uploader-visible fields there — review cases, summaries,
    and pipeline stages stay administrator-only.
    """
    try:
        return await service.list_own_files()
    except Exception as e:
        raise handle_exception(e)


@router.get("")
async def get_files(
    identity: AuthIdentity = Depends(require_admin),
    auth_service: AuthService = Depends(get_auth_service),
    service: FileService = Depends(get_file_service)
):
    """Get list of all files."""
    try:
        result = await service.list_files()
        users_by_id = {
            user["user_id"]: user
            for user in auth_service.list_users(identity)
        }
        for file_document in result.get("files", []):
            owner = users_by_id.get(file_document.get("owner_user_id"))
            if owner:
                file_document["owner_email"] = owner["email"]
                file_document["owner_display_name"] = owner["display_name"]
        return result
    except Exception as e:
        raise handle_exception(e)


@router.get("/{file_id}/summary")
async def get_file_summary(
    file_id: str,
    _identity: AuthIdentity = Depends(require_admin),
    service: FileService = Depends(get_file_service)
):
    """Get summary for a specific file."""
    try:
        return await service.get_file_summary(file_id)
    except Exception as e:
        raise handle_exception(e)


@router.get("/{file_id}/review-case")
async def get_review_case(
    file_id: str,
    _identity: AuthIdentity = Depends(require_admin),
    service: FileService = Depends(get_file_service)
):
    """Get review case details for a file."""
    try:
        return await service.get_review_case(file_id)
    except Exception as e:
        raise handle_exception(e)


@router.post("/{file_id}/review-decision")
async def submit_review_decision(
    file_id: str,
    decision: ReviewDecisionRequest,
    identity: AuthIdentity = Depends(require_admin),
    service: FileService = Depends(get_file_service)
):
    """Submit a review decision for a file."""
    try:
        trusted_decision = decision.model_dump(exclude_none=True)
        trusted_decision["reviewer"] = identity.user_id
        trusted_decision["reviewer_role"] = identity.role
        return await service.submit_review_decision(
            file_id,
            trusted_decision,
        )
    except Exception as e:
        raise handle_exception(e)


@router.get("/{file_id}/audit-trail")
async def get_audit_trail(
    file_id: str,
    cursor: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    _identity: AuthIdentity = Depends(require_admin),
    service: FileService = Depends(get_file_service)
):
    """Get audit trail for a file."""
    try:
        return await service.get_audit_trail(file_id, cursor=cursor, limit=limit)
    except Exception as e:
        raise handle_exception(e)


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    _identity: AuthIdentity = Depends(require_admin),
    service: FileService = Depends(get_file_service)
):
    """Delete a file."""
    try:
        return await service.delete_file(file_id)
    except Exception as e:
        raise handle_exception(e)


@router.post("/{file_id}/rerun")
async def rerun_stage(
    file_id: str,
    stage: str = Query(..., description="Stage to re-run"),
    _identity: AuthIdentity = Depends(require_admin),
    service: FileService = Depends(get_file_service)
):
    """Re-run a specific stage for a file."""
    try:
        return await service.rerun_stage(file_id, stage)
    except Exception as e:
        raise handle_exception(e)
