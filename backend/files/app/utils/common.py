"""Common utility functions."""
import base64
import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.core.constants import IngestionState

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.auth import attach_internal_auth_context


def validate_managed_file_path(
    upload_dir: str,
    tenant_id: str,
    file_id: str,
    file_path: str,
) -> Path:
    """Resolve a stored file path and prove it belongs to the tenant/file directory."""
    safe_tenant = "".join(char for char in tenant_id if char.isalnum() or char in {"-", "_"})
    safe_file_id = "".join(char for char in file_id if char.isalnum() or char in {"-", "_"})
    if safe_tenant != tenant_id or safe_file_id != file_id or not safe_tenant or not safe_file_id:
        raise ValueError("Invalid tenant or file identifier")
    base = Path(upload_dir).resolve()
    expected_directory = (base / safe_tenant / safe_file_id).resolve()
    candidate = Path(file_path).resolve()
    if candidate.parent != expected_directory or base not in candidate.parents:
        raise ValueError("File path is outside the managed tenant directory")
    return candidate


def setup_cors(app: FastAPI) -> None:
    """Allow only explicitly configured internal browser origins."""
    origins = [value.strip() for value in os.getenv("INTERNAL_CORS_ORIGINS", "").split(",") if value.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Content-Type", "X-Internal-Auth", "X-Request-ID", "X-Trace-ID"],
    )


def create_file_document(
    file_id: str,
    filename: str,
    file_path: str,
    content_type: str,
    size: int,
    *,
    document_id: Optional[str] = None,
    gridfs_file_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a file document structure.
    
    Args:
        file_id: Unique file identifier
        filename: Original filename
        file_path: Path where file is stored
        content_type: MIME type of the file
        size: File size in bytes
        
    Returns:
        File document dictionary
    """
    now = datetime.utcnow()
    return {
        "file_id": file_id,
        "document_id": document_id or file_id,
        "filename": filename,
        "path": file_path,
        "gridfs_file_id": gridfs_file_id,
        "summary": "",
        "status": "started",
        "review_status": "not_required",
        "current_task_id": None,
        "latest_review_case_id": None,
        "sanitized_text_version": 0,
        "accepted_risk_categories": [],
        "stage": {
            "extraction": "waiting",
            "review": "waiting",
            "chunking": "waiting",
            "summary": "waiting",
            "embedding": "waiting",
            "semantic": "waiting",
            "vector": "waiting",
            "metadata": "waiting"
        },
        "metadata": {},
        "suggested_questions": [],
        "content_type": content_type,
        "size": size,
        "created_at": now,
        "updated_at": now
    }


def create_file_task_document(
    task_id: str,
    file_doc: Dict[str, Any],
    *,
    graph_run_id: Optional[str] = None,
    request_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a new file ingestion task document."""
    now = datetime.utcnow()
    document_id = file_doc.get("document_id") or file_doc["file_id"]
    graph_run_id = graph_run_id or str(uuid.uuid4())
    request_context = request_context or {}
    return {
        "task_id": task_id,
        "file_id": file_doc["file_id"],
        "document_id": document_id,
        "graph_run_id": graph_run_id,
        "task_type": "file_ingestion",
        "status": "queued",
        "current_node": IngestionState.LOAD_EXTRACTION_RESULT.value,
        "attempt": 1,
        "checkpoint_id": None,
        "resume_token_hash": None,
        "resume_token_expires_at": None,
        "graph_state": {
            "file_id": file_doc["file_id"],
            "document_id": document_id,
            "task_id": task_id,
            "graph_run_id": graph_run_id,
            "gridfs_file_id": file_doc.get("gridfs_file_id"),
            "filename": file_doc["filename"],
            "extracted_text": None,
            "extracted_text_hash": None,
            "sanitized_text": None,
            "sanitized_text_version": 0,
            "issue_findings": [],
            "review_required": False,
            "review_case_id": None,
            "review_decision": None,
            "redaction_patch_map": [],
            "chunk_ids": [],
            "embedding_job_ids": [],
            "cleanup_required": False,
            "request_id": request_context.get("request_id"),
            "trace_id": request_context.get("trace_id"),
            "correlation_id": request_context.get("correlation_id"),
            "source_service": request_context.get("source_service"),
            "reply_to": request_context.get("reply_to"),
            "stream_to": request_context.get("stream_to"),
            "error": None,
        },
        "error": {
            "code": None,
            "message": None,
            "details": {},
        },
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }


def save_file_from_base64(
    content_b64: str,
    upload_dir: str,
    file_id: str
) -> bytes:
    """
    Decode base64 content and save to file.
    
    Args:
        content_b64: Base64 encoded file content
        upload_dir: Directory to save file in
        file_id: Unique file identifier
        
    Returns:
        Decoded file content as bytes
    """
    content = base64.b64decode(content_b64)
    
    # Determine file path
    if os.path.isabs(upload_dir):
        file_path = os.path.join(upload_dir, file_id)
    else:
        file_path = os.path.join(os.path.abspath(upload_dir), file_id)
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(content)
    
    return content


def generate_file_id() -> str:
    """Generate a unique file ID."""
    return str(uuid.uuid4())


def generate_task_id() -> str:
    """Generate a new task identifier."""
    return str(uuid.uuid4())


def generate_review_case_id() -> str:
    """Generate a new review case identifier."""
    return str(uuid.uuid4())


def generate_decision_id() -> str:
    """Generate a new review decision identifier."""
    return str(uuid.uuid4())


def generate_event_id() -> str:
    """Generate a new audit event identifier."""
    return str(uuid.uuid4())


def generate_message_id() -> str:
    """Generate a new transport-neutral message identifier."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.utcnow()


def iso_utcnow() -> str:
    """Return the current UTC timestamp in ISO format."""
    return utcnow().isoformat()


def hash_text(value: str) -> str:
    """Create a stable SHA-256 hash for text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_resume_token(ttl_seconds: int) -> Dict[str, Any]:
    """Create a one-time resume token and metadata."""
    token = secrets.token_urlsafe(24)
    return {
        "token": token,
        "token_hash": hash_text(token),
        "expires_at": utcnow() + timedelta(seconds=ttl_seconds),
    }


def build_snippet(text: str, start: int, end: int, max_chars: int) -> str:
    """Build a bounded text snippet centered around a span."""
    if not text:
        return ""
    safe_start = max(0, start)
    safe_end = min(len(text), max(end, safe_start))
    if safe_end - safe_start >= max_chars:
        return text[safe_start:safe_start + max_chars]
    remaining = max_chars - (safe_end - safe_start)
    pad_left = remaining // 2
    pad_right = remaining - pad_left
    snippet_start = max(0, safe_start - pad_left)
    snippet_end = min(len(text), safe_end + pad_right)
    snippet = text[snippet_start:snippet_end]
    return snippet[:max_chars]


def build_preview(text: str, max_chars: int) -> str:
    """Create a bounded preview for a chunk or text."""
    return (text or "")[:max_chars]


def apply_patch_map(text: str, patch_map: Iterable[Dict[str, Any]]) -> str:
    """Apply a patch map deterministically from the end of the string."""
    patched = text
    sorted_patches = sorted(patch_map, key=lambda item: (item["start"], item["end"]), reverse=True)
    for patch in sorted_patches:
        patched = (
            patched[:patch["start"]]
            + patch.get("replacement", "")
            + patched[patch["end"]:]
        )
    return patched


def validate_patch_map(text: str, patch_map: List[Dict[str, Any]]) -> None:
    """Validate patch spans against a source text."""
    if not patch_map:
        raise ValueError("patch_map must not be empty")
    ordered = sorted(patch_map, key=lambda item: (item["start"], item["end"]))
    previous_end = -1
    text_length = len(text)
    for patch in ordered:
        start = patch.get("start")
        end = patch.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            raise ValueError("Patch spans must be integers")
        if start < 0 or end < 0 or start >= end or end > text_length:
            raise ValueError("Patch span is out of bounds")
        if start < previous_end:
            raise ValueError("Patch spans must not overlap")
        previous_end = end


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[Dict[str, int]]:
    """Chunk text into overlapping character windows."""
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks: List[Dict[str, int]] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunks.append({"char_start": start, "char_end": end})
        if end == text_length:
            break
        start = end - chunk_overlap
    return chunks


def matches_any_phrase(text: str, phrases: Iterable[str]) -> bool:
    """Check whether a lower-cased text contains any of the phrases."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in phrases)


def build_message_envelope(
    *,
    message_type: str,
    action: str,
    source_service: str,
    target_service: str,
    request_id: Optional[str],
    trace_id: Optional[str],
    correlation_id: Optional[str],
    payload: Dict[str, Any],
    message_id: Optional[str] = None,
    reply_to: Optional[str] = None,
    stream_to: Optional[str] = None,
    success: Optional[bool] = None,
    error: Optional[Dict[str, Any]] = None,
    auth_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the shared Kafka envelope used across services."""
    resolved_request_id = request_id or correlation_id or generate_message_id()
    resolved_trace_id = trace_id or resolved_request_id
    resolved_correlation_id = correlation_id or resolved_request_id
    message = {
        "message_id": message_id or generate_message_id(),
        "message_type": message_type,
        "action": action,
        "source_service": source_service,
        "target_service": target_service,
        "request_id": resolved_request_id,
        "trace_id": resolved_trace_id,
        "correlation_id": resolved_correlation_id,
        "timestamp": iso_utcnow(),
        "payload": payload,
    }
    if auth_context:
        message["auth_context"] = auth_context
    else:
        attach_internal_auth_context(message)
    if reply_to:
        message["reply_to"] = reply_to
    if stream_to:
        message["stream_to"] = stream_to
    if message_type == "reply":
        message["success"] = bool(success)
        if error is not None:
            message["error"] = error
    return message


# Compatibility name retained for older handlers.
build_kafka_envelope = build_message_envelope
