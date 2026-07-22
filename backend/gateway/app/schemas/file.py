"""File-related Pydantic schemas."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class FileUploadResponse(BaseModel):
    """Response model for file upload."""
    file_id: str = Field(..., description="File ID")
    filename: str = Field(..., description="File name")
    status: str = Field(..., description="Upload status")
    document_id: Optional[str] = Field(default=None, description="Document ID")
    current_task_id: Optional[str] = Field(default=None, description="Current ingestion task ID")
    message: Optional[str] = Field(default=None, description="Status message")
    request_id: Optional[str] = Field(default=None, description="Correlation request ID")
    trace_id: Optional[str] = Field(default=None, description="Correlation trace ID")


class FileInfo(BaseModel):
    """File information model."""
    file_id: str = Field(..., description="File ID")
    filename: str = Field(..., description="File name")
    status: str = Field(..., description="File processing status")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")


class FileListResponse(BaseModel):
    """Response model for file list."""
    files: List[FileInfo] = Field(default_factory=list, description="List of files")


class FileSummaryResponse(BaseModel):
    """Response model for file summary."""
    file_id: str = Field(..., description="File ID")
    summary: Optional[str] = Field(default=None, description="File summary")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="File metadata")


class ReviewDecisionRequest(BaseModel):
    """Request model for file review decisions."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["delete_file", "remove_problematic_text", "accept_as_is"] = Field(
        ...,
        description="Review decision",
    )
    review_case_id: str = Field(..., min_length=1, max_length=200, description="Review case identifier")
    patch_map: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        max_length=500,
        description="Server-issued redaction patches selected by the administrator",
    )
    based_on_text_hash: Optional[str] = Field(
        default=None,
        description="Hash of the extracted text reviewed by the human decision",
    )
    notes: Optional[str] = Field(default=None, max_length=4000, description="Optional reviewer notes")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional decision metadata")
