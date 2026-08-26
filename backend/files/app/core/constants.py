"""Enums and fixed constants for the files service.

All message action names and other repeated literals must be imported from here
instead of appearing as inline strings elsewhere in the codebase.
"""
from enum import Enum


class FileAction(str, Enum):
    """Message action values consumed by FileService."""

    UPLOAD = "upload"
    START_FILE_INGESTION = "start_file_ingestion"
    COMPLETE_EXTRACTION = "complete_extraction"
    LIST = "list"
    LIST_OWN = "list_own"
    RESOLVE_FILE_LABELS = "resolve_file_labels"
    RESOLVE_CHUNK_LABELS = "resolve_chunk_labels"
    GET = "get"
    GET_SUGGESTED_QUESTIONS = "get_suggested_questions"
    GET_REVIEW_CASE = "get_review_case"
    SUBMIT_REVIEW_DECISION = "submit_review_decision"
    GET_AUDIT_TRAIL = "get_audit_trail"
    UPDATE_STAGE = "update_stage"
    UPDATE_SUMMARY = "update_summary"
    UPDATE_METADATA = "update_metadata"
    UPDATE_SUGGESTED_QUESTIONS = "update_suggested_questions"
    GET_SUMMARY = "get_summary"
    DELETE = "delete"
    RERUN_STAGE = "rerun_stage"
    GET_METRICS = "get_metrics"
