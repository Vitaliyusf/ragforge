"""Gateway service constants, enums, and fixed parameters."""
from enum import Enum

# ── Limits ────────────────────────────────────────────────────────────────────
HISTORY_MESSAGE_LIMIT: int = 3         # Raw messages appended after compressed summary

# ── Timeouts ──────────────────────────────────────────────────────────────────
VECTOR_CLEANUP_TIMEOUT: float = 15.0   # Best-effort vector DB cleanup after file delete

# ── HTTP error code → slug mapping ────────────────────────────────────────────
HTTP_ERROR_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    408: "request_timeout",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
    504: "gateway_timeout",
}

# ── Service topology ──────────────────────────────────────────────────────────
SERVICE_PORTS: dict[str, int] = {
    "gateway":   8000,
    "llm_agent": 8001,
    "embedding": 8002,
    "reranker":  8003,
    "rag":       8004,
    "files":     8005,
    "vector_db": 8006,
    "memory":    8007,
}

# ── Domain Enums ──────────────────────────────────────────────────────────────

class AnswerMode(str, Enum):
    """Supported answer verbosity modes for chat requests."""
    QUICK = "quick"
    EXTENDED = "extended"


class ReviewDecision(str, Enum):
    """Valid decisions for a file review case."""
    DELETE_FILE = "delete_file"
    REMOVE_PROBLEMATIC_TEXT = "remove_problematic_text"
    ACCEPT_AS_IS = "accept_as_is"


class LLMImplementation(str, Enum):
    """Supported LLM backend implementations."""
    HUGGINGFACE = "huggingface"
    VLLM = "vllm"
    OLLAMA = "ollama"


# ── Kafka Action Names ────────────────────────────────────────────────────────

class MemoryAction(str, Enum):
    """Action strings routed to the memory service."""
    CREATE_CHAT = "create_chat"
    GET_CHATS = "get_chats"
    GET_MESSAGES = "get_messages"
    ADD_MESSAGE = "add_message"
    DELETE_CHAT = "delete_chat"
    PROCESS_CHAT_EXIT = "process_chat_exit"
    UPDATE_CHAT_TITLE = "update_chat_title"
    GET_COMPRESSED_HISTORY = "get_compressed_history"
    GET_USER_INSIGHT = "get_user_insight"
    UPDATE_USER_INSIGHT = "update_user_insight"
    GET_LONG_TERM_MEMORIES = "get_long_term_memories"
    CREATE_LONG_TERM_MEMORY = "create_long_term_memory"
    UPDATE_LONG_TERM_MEMORY = "update_long_term_memory"
    DELETE_LONG_TERM_MEMORY = "delete_long_term_memory"


class FileAction(str, Enum):
    """Action strings routed to the files service."""
    START_FILE_INGESTION = "start_file_ingestion"
    LIST = "list"
    LIST_OWN = "list_own"
    GET_SUMMARY = "get_summary"
    GET_REVIEW_CASE = "get_review_case"
    SUBMIT_REVIEW_DECISION = "submit_review_decision"
    GET_AUDIT_TRAIL = "get_audit_trail"
    DELETE = "delete"
    RERUN_STAGE = "rerun_stage"
    GET_SUGGESTED_QUESTIONS = "get_suggested_questions"


class RagAction(str, Enum):
    """Action strings routed to the RAG service."""
    QUERY = "query"
    GENERATE = "generate"
    GET_TRACE = "get_trace"
    SUBMIT_FEEDBACK = "submit_feedback"


class VectorDbAction(str, Enum):
    """Action strings routed to the vector DB service."""
    DELETE_BY_FILE_ID = "delete_by_file_id"


class ConfigManagementAction(str, Enum):
    """Action strings routed to the config management service."""
    GET_CONFIG = "get_config"
    UPDATE_CONFIG = "update_config"
    GET_GENERATION_PARAMS = "get_generation_params"
    UPDATE_GENERATION_PARAMS = "update_generation_params"
    SWITCH_IMPLEMENTATION = "switch_implementation"
    GET_MODEL_CONFIGS = "get_model_configs"
    UPDATE_MODEL_CONFIGS = "update_model_configs"


class ModelManagementAction(str, Enum):
    """Action strings routed to the model management service."""
    LLM_READY = "llm_ready"
    LIST_IMPLEMENTATIONS = "list_implementations"
    GET_IMPLEMENTATION_INFO = "get_implementation_info"
    LIST_MODELS = "list_models"
    GET_MODEL_INFO = "get_model_info"
    DOWNLOAD_MODEL = "download_model"
    GET_DOWNLOAD_STATUS = "get_download_status"


class ModelsAction(str, Enum):
    """Action strings routed to the legacy models topic."""
    FETCH_MODELS = "fetch_models"
