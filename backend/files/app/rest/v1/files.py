"""Service-local file lookup endpoint."""
from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_file_repository
from app.db.repository import FileRepository
from shared.auth import AuthIdentity
from shared.http_auth import require_internal_identity

router = APIRouter()


@router.get("/files/{file_id}")
async def get_file(
    file_id: str,
    _identity: AuthIdentity = Depends(require_internal_identity),
    repository: FileRepository = Depends(get_file_repository),
) -> dict:
    """Return a serialized file document by ``file_id``.

    Args:
        file_id: File identifier stored in the ``files`` collection.
        repository: Repository dependency used to fetch the file record.

    Returns:
        dict: Serialized file document including review and stage fields.

    Raises:
        HTTPException: 404 when the file is not found.
    """
    file_doc = repository.get_by_id(file_id)
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")
    return file_doc
