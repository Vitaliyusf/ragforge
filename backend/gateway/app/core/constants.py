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

# ── Model pricing ─────────────────────────────────────────────────────
# Estimated price per 1,000 tokens as ``(input, output)``, in USD.
#
# Every model this repository ships with runs on self-hosted vLLM, where
# there is no per-token charge, so the honest price is 0.0. Add hosted
# models here with their real published rates when one is configured.
#
# This table is the single source of truth for pricing. The rag service
# returns token sums only and applies no price of its own, so the two can
# never drift apart.
MODEL_COST_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "RedHatAI/Qwen3.5-4B-quantized.w4a16": (0.0, 0.0),
}

# Unknown models assume no price rather than a guessed one. Metrics
# responses list any such model under ``models_without_pricing``, so a
# $0.00 total reads as "nothing here is priced" rather than as a measured
# zero that someone could quote in a review deck.
DEFAULT_MODEL_COST_PER_1K_TOKENS: tuple[float, float] = (0.0, 0.0)

# ── Eval run cost estimation ──────────────────────────────────────────
# An `end_to_end` eval run spends tokens per item: one generation call and
# one judge call, each carrying the retrieved context. These are coarse
# per-item averages used only to warn an admin before they start a run, and
# the UI must present the result as an estimate, never as a bill.
EVAL_END_TO_END_TOKENS_PER_ITEM: tuple[int, int] = (2_400, 400)


# ── Domain Enums ──────────────────────────────────────────────────────────────

class AnswerMode(str, Enum):
    """Supported answer verbosity modes for chat requests."""
    QUICK = "quick"
    EXTENDED = "extended"


class EvalRunMode(str, Enum):
    """How much of the pipeline an eval run exercises.

    ``RETRIEVAL`` is the default everywhere the mode is optional: it calls no
    model, finishes a 200-item dataset in seconds, and costs nothing.
    ``END_TO_END`` additionally generates and judges an answer per item, so
    it spends tokens and is opt-in per run.
    """
    RETRIEVAL = "retrieval"
    END_TO_END = "end_to_end"


class EvalPipelineMode(str, Enum):
    """Which conversation pipeline an ``end_to_end`` eval run drives.

    A different axis from :class:`EvalRunMode`, which says how much of the
    stack a run measures. A ``retrieval`` run drives no pipeline at all — its
    single search is not routed through one — so leaving this unset is the
    correct answer for it, not a missing value.
    """
    REGULAR = "regular"
    EXTENDED = "extended"


class BenchmarkPhase(str, Enum):
    """The phases a full diagnostic benchmark can be asked for.

    Mirrors ``PHASE_SPECS`` in the rag service's
    ``app/services/benchmark_runner.py``, which cannot import gateway code —
    the same arrangement as :class:`RagAction`. Naming a phase here does not
    promise it will run: rag decides which phases this build can execute
    truthfully and records the rest as ``unsupported`` with the reason.
    """
    RETRIEVAL_BASE = "retrieval_base"
    RETRIEVAL_EXTENDED = "retrieval_extended"
    END_TO_END_REGULAR = "end_to_end_regular"
    END_TO_END_EXTENDED = "end_to_end_extended"


class MetricsWindow(str, Enum):
    """Allowed lookback windows for the admin metrics routes.

    A fixed allow-list: route handlers annotate their query parameter with
    this type, so FastAPI rejects anything else with a 422 long before any
    value could reach a PromQL expression or a MongoDB pipeline.
    """
    HOUR = "1h"
    DAY = "24h"
    WEEK = "7d"
    MONTH = "30d"


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
    GENERATE_TITLE = "generate_title"
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
    GET_METRICS = "get_metrics"


class RagAction(str, Enum):
    """Action strings routed to the RAG service."""
    QUERY = "query"
    GENERATE = "generate"
    GET_TRACE = "get_trace"
    SUBMIT_FEEDBACK = "submit_feedback"
    GET_METRICS = "get_metrics"
    # Retrieval eval harness. These values are mirrored as literals in the
    # rag service's app/services/eval_runner.py, which cannot import gateway
    # code — the same arrangement as GET_METRICS and METRICS_ACTION.
    LIST_EVAL_DATASETS = "list_eval_datasets"
    CREATE_EVAL_DATASET = "create_eval_dataset"
    VALIDATE_EVAL_DATASET = "validate_eval_dataset"
    UPDATE_EVAL_DATASET = "update_eval_dataset"
    DELETE_EVAL_DATASET = "delete_eval_dataset"
    START_EVAL_RUN = "start_eval_run"
    LIST_EVAL_RUNS = "list_eval_runs"
    GET_EVAL_RUN = "get_eval_run"
    # Full diagnostic benchmark orchestration. Each phase it runs is an
    # ordinary eval run, reachable through the eval actions above.
    START_BENCHMARK_RUN = "start_benchmark_run"
    LIST_BENCHMARK_RUNS = "list_benchmark_runs"
    GET_BENCHMARK_RUN = "get_benchmark_run"
    EXPORT_BENCHMARK_RUN = "export_benchmark_run"


class VectorDbAction(str, Enum):
    """Action strings routed to the vector DB service."""
    DELETE_BY_FILE_ID = "delete_by_file_id"
    GET_METRICS = "get_metrics"


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
