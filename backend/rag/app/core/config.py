"""Configuration management for the RAG service."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGConfig(BaseSettings):
    """Configuration class for the `rag` service."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Service configuration
    service_name: str = "rag"
    service_port: int = 8004
    service_host: str = "0.0.0.0"

    # RabbitMQ configuration (inbound and downstream RPC transport)
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "ragapp.requests"
    rabbitmq_queue: str = "rag"
    rabbitmq_prefetch_count: int = 1
    rabbitmq_rpc_max_inflight: int = 64

    # Direct-exchange routing keys for downstream service calls.
    memory_routing_key: str = "memory"
    llm_agent_routing_key: str = "llm_agent"
    vector_db_routing_key: str = "vector_db"
    embedding_routing_key: str = "embedding"
    files_routing_key: str = "files"

    # Mongo persistence
    conversation_store_type: str = "mongodb"
    mongodb_url: str = "mongodb://localhost:27017/"
    mongodb_database: str = "rag"
    mongodb_max_retries: int = 10
    mongodb_retry_delay: int = 2
    persistence_max_concurrency: int = 4

    # CORS configuration
    frontend_url: str = "http://localhost:3000"
    internal_auth_secret: str = "development-only-internal-auth-secret-change-me"
    socket_connection_ttl_seconds: int = 28_800

    # Runtime configuration
    internal_request_timeout: float = 75.0
    generation_request_timeout: float = 120.0
    evaluation_request_timeout: float = 75.0
    top_k_documents: int = 6
    hybrid_search_enabled: bool = True
    dense_candidate_k: int = 20
    sparse_candidate_k: int = 20
    hybrid_rrf_k: int = 60
    # Final generation input is bounded independently of retrieval depth.
    # The assembler first reserves space for the question, instructions and
    # provider-owned system/chat framing, then applies this evidence ceiling.
    generation_input_token_budget: int = 6144
    generation_system_prompt_reserve_tokens: int = 512
    context_token_budget: int = 3072
    context_diversity_score_tolerance: float = 0.08
    max_recent_messages: int = 6
    max_memory_hits: int = 6
    min_similarity_threshold: float = 0.4
    pass_two_chunk_threshold: int = 3
    pass_two_score_threshold: float = 0.55
    extended_retrieval_max_concurrency: int = 4
    debug_payload_max_chars: int = 2000
    debug_payload_max_items: int = 12
    feedback_memory_threshold: int = 3

    # Guardrail / UX behavior
    enable_retrieval_bypass: bool = True
    retrieval_bypass_max_length: int = 20
    enable_langsmith_tracing: bool = True
    langsmith_project: str = "rag"
    allow_debug_payloads: bool = True
    stream_poll_interval_seconds: float = 0.1
    stream_idle_timeout_seconds: float = 5.0
    stream_drain_timeout_seconds: float = 1.0
    approved_stream_emit_timeout_seconds: float = 5.0

    # Learned reranker. The production compose profile enables it after baking
    # the pinned model into the image; local source-only runs degrade cleanly.
    vector_store_type: str = "in_memory"
    reranker_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_model_revision: str = "b5160aeac3c6c8fe7beaaaf04c9e0142826b58d1"
    reranker_candidate_k: int = 20
    reranker_timeout_seconds: float = 5.0
    reranker_batch_size: int = 8
    reranker_max_length: int = 512

    # Collection names
    conversation_threads_collection: str = "conversation_threads"
    conversation_turns_collection: str = "conversation_turns"
    conversation_summaries_collection: str = "conversation_summaries"
    graph_checkpoints_collection: str = "graph_checkpoints"
    answer_reviews_collection: str = "answer_reviews"
    user_feedback_collection: str = "user_feedback"
    flow_feedback_collection: str = "flow_feedback"
    metrics_turn_facts_collection: str = "metrics_turn_facts"
    eval_datasets_collection: str = "eval_datasets"
    eval_runs_collection: str = "eval_runs"
    eval_benchmark_runs_collection: str = "eval_benchmark_runs"

    # Admin metrics retention
    metrics_retention_days: int = 90

    # Optional operational evidence for benchmark artifacts. A monitoring
    # outage must never prevent an evaluation from running.
    prometheus_url: str = "http://prometheus:9090"

    # Retrieval eval harness.
    #
    # `eval_run_concurrency` bounds the semaphore in `eval_runner`. Raising
    # it does not make a run finish sooner: the embedding service is the
    # bottleneck, and an unbounded fan-out over a 200-item dataset buries it
    # while live traffic is still being served by the same instance.
    eval_run_concurrency: int = 4
    # A process-local eval worker must renew this lease while it is doing
    # work.  Startup reconciliation closes stale work rather than guessing
    # whether an interrupted scorer can safely be replayed.
    eval_lease_seconds: int = 300
    # How many candidates a retrieval eval asks the vector store for.
    #
    # Deliberately separate from `top_k_documents`, which sizes the context an
    # answer is generated from and is tuned for cost and prompt length. A run
    # reporting Recall@20 must actually look at twenty candidates: scoring
    # Recall@20 over six of them can only ever report the Recall@6 number
    # under a wider name. `eval_runner` raises this to max(K_VALUES) if it is
    # ever configured lower, because a k the run cannot observe is not a
    # measurement. The vector_db payload caps top_k at 100.
    eval_candidate_k: int = 20
    # Upload limits. Enforced in `eval_store` even though the gateway checks
    # them too — an RPC caller is not automatically the gateway, the same
    # reason `metrics_query` re-validates its window on arrival.
    eval_max_dataset_items: int = 1000
    eval_max_query_length: int = 2000
    eval_max_name_length: int = 200
    eval_max_dataset_bytes: int = 5 * 1024 * 1024
    # Terminal eval/benchmark runs are diagnostic artifacts rather than
    # permanent business records. MongoDB TTL indexes remove them after this
    # window; active work has no ``finished_at`` and is therefore never
    # expired underneath a worker.
    eval_artifact_retention_days: int = 90

    # Stale-label detection.
    #
    # A golden set labelled against an older index can name chunks or files
    # that reindexing or a chunking change has since removed. Retrieval
    # cannot return an id that no longer exists, so scoring those labels as
    # misses reports a recall regression that never happened. Before a run
    # scores anything, `eval_runner` asks vector_db which of the labelled ids
    # still exist in the caller's own tenant.
    eval_validate_labels: bool = True
    # What a run does when it finds stale labels. `fail` is the default
    # because a golden set whose ground truth has rotted is not measuring
    # retrieval any more, and a number nobody can trust is worse than no
    # number. `mark_unscorable` is for teams who would rather keep the
    # remaining items: affected items are excluded from every mean and
    # reported separately, never counted as misses.
    eval_stale_label_policy: str = "fail"
    # How many affected ids a run stores for the drill-down. The counts are
    # always exact; the id lists are a sample, because a dataset that went
    # wholly stale would otherwise write its entire label set into the run
    # document.
    eval_max_reported_stale_ids: int = 50

    # Per-item retrieval diagnostics.
    #
    # A trace explains one item's candidate movement: what each retrieval
    # step returned, which branch the pipeline took, and where the finally
    # selected chunks entered the ranking. It is collected only when an eval
    # item asks for one, so a user's turn carries no trace at all.
    #
    # The bounds are what keep a drill-down from becoming a copy of the
    # index. Candidate text is never stored at any bound: a trace holds ids,
    # ranks and scores only.
    eval_trace_max_candidates: int = 20
    eval_trace_max_stages: int = 12
    eval_trace_max_query_chars: int = 200

    # A turn whose groundedness falls below this counts toward the proxy
    # hallucination rate. It is a threshold over one judge score, not a
    # claim-level measurement — phase 6 replaces it with the real thing.
    hallucination_groundedness_threshold: float = 0.6

    def validate(self) -> bool:
        """Validate configuration values."""
        if not self.rabbitmq_url:
            return False
        return True


# Convenience alias used by RabbitMQ implementation modules.
Settings = RAGConfig
