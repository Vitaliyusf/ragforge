"""Service-wide constants and enums.

All magic strings for LLM implementations and message action names must be
referenced from here.  Never use bare string literals for these values in
service or handler code.
"""
from enum import Enum


class LLMImplementation(str, Enum):
    """Supported LLM backend identifiers."""

    HUGGINGFACE = "huggingface"
    VLLM = "vllm"
    OLLAMA = "ollama"


VALID_IMPLEMENTATIONS: frozenset = frozenset(m.value for m in LLMImplementation)


class FilesAction(str, Enum):
    """Action names published fire-and-forget to the files service."""

    UPDATE_SUMMARY = "update_summary"
    UPDATE_METADATA = "update_metadata"
    UPDATE_SUGGESTED_QUESTIONS = "update_suggested_questions"


class ConfigAction(str, Enum):
    """Action names handled by ConfigManagementHandler."""

    GET_CONFIG = "get_config"


class LLMRequestType(str, Enum):
    """Typed request type discriminators used in message envelopes."""

    ANSWER_GENERATION = "answer_generation"
    ANSWER_EVALUATION = "answer_evaluation"
    CONTENT_RISK_SCAN = "content_risk_scan"
    QUERY_REWRITE = "query_rewrite"
    MEMORY_EXTRACTION = "memory_extraction"
    GENERATE_QUESTIONS = "generate_questions"
    SUMMARIZE = "summarize"


# Service identifier constant
SOURCE_SERVICE: str = "llm_agent"
