"""The deployed vLLM runtime contract a benchmark comparison depends on.

An A/B between two vLLM versions is only evidence if exactly one thing moved.
These tests pin the everything-else: the tuning knobs that must stay where the
last winning benchmark left them, the model runner WSL2 cannot do without, the
scheduler flags this upgrade deliberately does not touch, and the readiness and
scrape wiring that keeps cold-start cost and vLLM's own metrics from being
guessed at.

Read as plain text rather than parsed as YAML on purpose: PyYAML is not a
dependency of this repository, and adding one so a guardrail test can run is a
worse trade than a small indentation-aware reader.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
PROMETHEUS = (REPO_ROOT / "docker" / "prometheus" / "prometheus.yml").read_text(
    encoding="utf-8"
)
ENV_EXAMPLE = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")


def service_block(name: str) -> str:
    """The lines of one Compose service, from its key to the next sibling."""
    lines = COMPOSE.splitlines()
    header = f"  {name}:"
    start = next(i for i, line in enumerate(lines) if line == header)
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].strip() and not lines[i].startswith("   ")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


VLLM = service_block("vllm")
LLM_AGENT = service_block("llm_agent")
MEMORY = service_block("memory")
RAG = service_block("rag")
PROMETHEUS_SERVICE = service_block("prometheus")


# ── Version under test ──────────────────────────────────────


def test_the_default_image_is_the_pinned_candidate_release():
    assert "image: ${VLLM_IMAGE:-vllm/vllm-openai:v0.28.0}" in VLLM


def test_the_image_is_never_a_floating_tag():
    """`latest`/`nightly`/`main` name no version, so no run could cite one."""
    for floating in (":latest", ":nightly", ":main"):
        assert f"vllm/vllm-openai{floating}" not in COMPOSE
        assert f"vllm/vllm-openai{floating}" not in ENV_EXAMPLE


def test_the_documented_environment_pins_the_same_release():
    assert "VLLM_IMAGE=vllm/vllm-openai:v0.28.0" in ENV_EXAMPLE


# ── What the upgrade must not change ────────────────────────


def test_the_v2_model_runner_stays_disabled_by_default():
    """WSL2 has no CUDA UVA, and 0.28 still ships no safe fallback for it."""
    assert "VLLM_USE_V2_MODEL_RUNNER: ${VLLM_USE_V2_MODEL_RUNNER:-0}" in VLLM
    assert "VLLM_USE_V2_MODEL_RUNNER=0" in ENV_EXAMPLE


def test_the_scheduler_concurrency_candidate_is_still_explicit():
    assert '- "${VLLM_MAX_NUM_SEQS:-4}"' in VLLM
    assert "VLLM_MAX_NUM_SEQS=4" in ENV_EXAMPLE


def test_the_memory_allocation_is_still_explicit():
    assert '- "${VLLM_GPU_MEMORY_UTILIZATION:-0.80}"' in VLLM
    assert "VLLM_GPU_MEMORY_UTILIZATION=0.80" in ENV_EXAMPLE


def test_the_serving_flags_this_workload_was_tuned_under_are_intact():
    for flag in (
        "--language-model-only",
        "--enable-prefix-caching",
        "--quantization",
        "--max-model-len",
        "--reasoning-parser",
        "--tool-call-parser",
    ):
        assert flag in VLLM


def test_no_new_scheduler_knob_is_tuned_in_the_upgrade_only_run():
    """One variable moves per experiment, or the result attributes nothing."""
    for flag in (
        "--max-num-batched-tokens",
        "--max-num-scheduled-tokens",
        "--performance-mode",
        "--async-scheduling",
        "--enable-chunked-prefill",
        "--stream-interval",
        "--watermark",
        "--kv-cache-memory-bytes",
    ):
        assert flag not in VLLM, f"{flag} changes a second variable"


def test_speculative_decoding_stays_off():
    for flag in ("--speculative", "speculative_config", "--num-speculative-tokens"):
        assert flag not in VLLM


def test_the_per_action_token_budgets_are_unchanged():
    budgets = {
        "ANSWER_GENERATION_MAX_TOKENS": 128,
        "ANSWER_EVALUATION_MAX_TOKENS": 512,
        "CONTENT_RISK_SCAN_MAX_TOKENS": 128,
        "QUERY_REWRITE_MAX_TOKENS": 128,
        "MEMORY_EXTRACTION_MAX_TOKENS": 512,
    }
    for name, value in budgets.items():
        expected = f"{name}: ${{{name}:-{value}}}"
        assert expected in LLM_AGENT, f"llm_agent budget moved: {name}"
        assert expected in RAG, f"rag provenance budget moved: {name}"


def test_the_queue_prefetch_is_unchanged():
    assert "LLM_REQUEST_PREFETCH: ${LLM_REQUEST_PREFETCH:-4}" in LLM_AGENT


# ── Readiness ───────────────────────────────────────────────


def test_vllm_declares_a_healthcheck():
    """"The container exists" is not "the OpenAI server answers"."""
    assert "healthcheck:" in VLLM
    assert "/health" in VLLM


def test_the_healthcheck_does_no_generation_work():
    """A healthcheck that generated would compete with the benchmark."""
    assert "/v1/chat/completions" not in VLLM
    assert "/v1/completions" not in VLLM


def test_the_healthcheck_tolerates_a_slow_cold_start():
    """Weight download plus graph capture must not count as failures."""
    assert "start_period:" in VLLM


def test_consumers_wait_for_a_healthy_server_not_a_started_one():
    for consumer, block in (("llm_agent", LLM_AGENT), ("memory", MEMORY)):
        marker = "      vllm:\n        condition: service_healthy"
        assert marker in block, f"{consumer} may start against a loading vLLM"


# ── Metrics boundary ────────────────────────────────────────


def test_prometheus_scrapes_the_vllm_server():
    assert "job_name: vllm" in PROMETHEUS
    assert 'targets: ["vllm:8000"]' in PROMETHEUS


def test_prometheus_can_reach_the_internal_ai_network():
    assert "networks: [messaging, ai]" in PROMETHEUS_SERVICE


def test_vllm_metrics_are_not_published_to_the_host_or_lan():
    """Scraping vLLM internally is not a reason to expose its port."""
    assert "ports:" not in VLLM


def test_the_ai_network_stays_internal():
    assert "  ai:\n    internal: true" in COMPOSE


# ── Benchmark provenance wiring ─────────────────────────────


def test_rag_receives_the_vllm_provenance_it_records():
    """Every value the manifest reports must be injected, never inferred."""
    for variable in (
        "VLLM_IMAGE:",
        "VLLM_USE_V2_MODEL_RUNNER:",
        "VLLM_MAX_NUM_SEQS:",
        "VLLM_GPU_MEMORY_UTILIZATION:",
        "VLLM_MAX_MODEL_LEN:",
        "VLLM_QUANTIZATION:",
        "VLLM_PREFIX_CACHING:",
    ):
        assert variable in RAG


def test_rag_provenance_cannot_drift_from_the_served_runtime():
    """The same ${VAR:-default} feeds the server and the manifest."""
    for expression in (
        "${VLLM_IMAGE:-vllm/vllm-openai:v0.28.0}",
        "${VLLM_MAX_NUM_SEQS:-4}",
        "${VLLM_GPU_MEMORY_UTILIZATION:-0.80}",
        "${VLLM_MAX_MODEL_LEN:-10240}",
        "${VLLM_USE_V2_MODEL_RUNNER:-0}",
    ):
        assert expression in RAG
        assert expression in VLLM


def test_prefix_caching_provenance_matches_the_served_flag():
    assert "--enable-prefix-caching" in VLLM
    assert 'VLLM_PREFIX_CACHING: "true"' in RAG


def test_no_scheduler_tuning_variable_is_injected_for_the_control_run():
    """Unset is the recorded value; an injected one would tune the run."""
    for variable in (
        "VLLM_MAX_NUM_BATCHED_TOKENS",
        "VLLM_PERFORMANCE_MODE",
        "VLLM_ASYNC_SCHEDULING",
        "VLLM_ENABLE_CHUNKED_PREFILL",
        "VLLM_SCHEDULER_RESERVE_FULL_ISL",
    ):
        assert variable not in COMPOSE


def test_the_vllm_api_key_is_not_handed_to_the_provenance_recorder():
    assert "VLLM_API_KEY" not in RAG
