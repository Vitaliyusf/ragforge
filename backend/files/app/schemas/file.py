"""Pydantic models for service-local file documents and legacy request shapes."""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class FileDocument(BaseModel):
    """Serialized file record exposed by service-local HTTP and Kafka replies."""
    file_id: str
    document_id: Optional[str] = None
    filename: str
    path: str = ""
    gridfs_file_id: Optional[str] = None
    summary: str = ""
    status: str = "started"
    review_status: str = "not_required"
    current_task_id: Optional[str] = None
    latest_review_case_id: Optional[str] = None
    sanitized_text_version: int = 0
    accepted_risk_categories: List[str] = Field(default_factory=list)
    stage: Dict[str, str] = Field(
        default_factory=lambda: {
            "extraction": "waiting",
            "review": "waiting",
            "chunking": "waiting",
            "summary": "waiting",
            "embedding": "waiting",
            "semantic": "waiting",
            "vector": "waiting",
            "metadata": "waiting"
        }
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)
    content_type: str = "application/octet-stream"
    size: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UploadRequest(BaseModel):
    """Legacy base64 upload schema retained for older callers.

    The active gateway-mediated upload path stores bytes in GridFS and sends a
    metadata handle such as `gridfs_file_id` over Kafka instead of using this
    base64 request model.
    """
    filename: str
    content: str = Field(..., description="Base64 encoded file content")
    content_type: str = Field(default="application/octet-stream", description="MIME type")


class FileListResponse(BaseModel):
    """Response wrapper for serialized file-document lists."""
    files: List[FileDocument]


class FileSummaryResponse(BaseModel):
    """Response model for the stored file summary stage."""
    summary: str
    stage: str
