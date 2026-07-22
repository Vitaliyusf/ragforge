"""Long-term memory API routes."""
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, Body

from app.core.deps import get_long_term_memory_service
from app.core.errors import handle_exception
from app.services.long_term_memory_service import LongTermMemoryService
from app.core.auth import get_current_user

router = APIRouter(prefix="/long-term-memory", tags=["long-term-memory"], dependencies=[Depends(get_current_user)])


@router.get("")
async def get_all_memories(
    service: LongTermMemoryService = Depends(get_long_term_memory_service)
):
    """Return the current list of long-term-memory entries from the memory service."""
    try:
        return await service.get_all_memories()
    except Exception as e:
        raise handle_exception(e)


@router.post("")
async def create_memory(
    content: str = Body(...),
    category: Optional[str] = Body(None),
    metadata: Optional[Dict[str, Any]] = Body(None),
    service: LongTermMemoryService = Depends(get_long_term_memory_service)
):
    """Create a long-term-memory entry.

    Parameters:
        content: Primary memory text stored by the downstream memory service.
        category: Optional category label forwarded without mutation.
        metadata: Optional JSON-like metadata forwarded without mutation.

    Returns:
        The downstream memory-service response for the created entry.
    """
    try:
        return await service.create_memory(content, category, metadata)
    except Exception as e:
        raise handle_exception(e)


@router.put("/{memory_id}")
async def update_memory(
    memory_id: str,
    content: Optional[str] = Body(None),
    category: Optional[str] = Body(None),
    metadata: Optional[Dict[str, Any]] = Body(None),
    service: LongTermMemoryService = Depends(get_long_term_memory_service)
):
    """Update a long-term-memory entry by identifier.

    Parameters:
        memory_id: Downstream memory identifier.
        content: Optional replacement content.
        category: Optional replacement category.
        metadata: Optional replacement metadata.

    Returns:
        The downstream memory-service response for the update request.
    """
    try:
        return await service.update_memory(memory_id, content, category, metadata)
    except Exception as e:
        raise handle_exception(e)


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    service: LongTermMemoryService = Depends(get_long_term_memory_service)
):
    """Delete a long-term-memory entry and return the downstream result."""
    try:
        return await service.delete_memory(memory_id)
    except Exception as e:
        raise handle_exception(e)


@router.get("/user-insight")
async def get_user_insight(
    service: LongTermMemoryService = Depends(get_long_term_memory_service)
):
    """Return the current user-insight summary maintained by the memory service."""
    try:
        return await service.get_user_insight()
    except Exception as e:
        raise handle_exception(e)


@router.put("/user-insight")
async def update_user_insight(
    insight: str = Body(...),
    service: LongTermMemoryService = Depends(get_long_term_memory_service)
):
    """Update the user-insight summary stored by the memory service.

    Parameters:
        insight: Replacement insight text forwarded to the downstream memory service.

    Returns:
        The downstream memory-service response for the update request.
    """
    try:
        return await service.update_user_insight(insight)
    except Exception as e:
        raise handle_exception(e)
