"""Chunk-native REST API endpoints for local/admin operations."""
from fastapi import APIRouter, Depends

from app.core.deps import get_vector_service
from app.core.errors import handle_vector_db_error
from app.schemas.vector import (
    ChunkDeleteApiRequest,
    ChunkOperationResponse,
    ChunkSearchApiRequest,
    ChunkSearchResult,
    ChunkUpsertApiRequest,
)
from app.services.vector_service import VectorService
from shared.http_auth import require_internal_admin

router = APIRouter(dependencies=[Depends(require_internal_admin)])


@router.post("/chunks/upsert", response_model=ChunkOperationResponse)
async def upsert_chunks(
    request: ChunkUpsertApiRequest,
    service: VectorService = Depends(get_vector_service),
) -> ChunkOperationResponse:
    """Upsert chunk payloads for local or admin flows."""
    try:
        result = service.upsert_chunks(
            chunks=[chunk.model_dump() for chunk in request.chunks],
            review_outcome=request.review_outcome,
            target_filters=(
                request.target_filters.model_dump(exclude_none=True)
                if request.target_filters
                else None
            ),
        )
        return ChunkOperationResponse(
            success=True,
            message="Chunks upserted successfully",
            collection_name=result["collection_name"],
            upserted_count=result["upserted_count"],
            deleted_count=result["deleted_count"],
        )
    except Exception as exc:
        raise handle_vector_db_error(exc)


@router.post("/chunks/search", response_model=ChunkOperationResponse)
async def search_chunks(
    request: ChunkSearchApiRequest,
    service: VectorService = Depends(get_vector_service),
) -> ChunkOperationResponse:
    """Search chunks while preserving the internal retrieval safety filter."""
    try:
        results = service.search_chunks(
            query_vector=request.query_vector,
            top_k=request.top_k,
            filters=request.filters.model_dump(exclude_none=True),
            include_payload=request.include_payload,
            include_vector=request.include_vector,
        )
        return ChunkOperationResponse(
            success=True,
            message="Chunk search completed successfully",
            collection_name=service.vector_store.collection_name,
            results=[ChunkSearchResult(**r) for r in results],
        )
    except Exception as exc:
        raise handle_vector_db_error(exc)


@router.delete("/chunks", response_model=ChunkOperationResponse)
async def delete_chunks(
    request: ChunkDeleteApiRequest,
    service: VectorService = Depends(get_vector_service),
) -> ChunkOperationResponse:
    """Hard delete chunks by canonical file or document filters."""
    try:
        deleted_count = service.delete_chunks(
            request.filters.model_dump(exclude_none=True)
        )
        return ChunkOperationResponse(
            success=True,
            message="Chunks deleted successfully",
            collection_name=service.vector_store.collection_name,
            deleted_count=deleted_count,
        )
    except Exception as exc:
        raise handle_vector_db_error(exc)


@router.post("/chunks/initialize", response_model=ChunkOperationResponse)
async def initialize_collection(
    service: VectorService = Depends(get_vector_service),
) -> ChunkOperationResponse:
    """Initialize the configured vector store collection and payload indexes."""
    try:
        collection_name = service.initialize_collection()
        return ChunkOperationResponse(
            success=True,
            message="Collection initialized successfully",
            collection_name=collection_name,
        )
    except Exception as exc:
        raise handle_vector_db_error(exc)
