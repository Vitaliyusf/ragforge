"""Tests for the automatic benchmark manifest.

Two things are being defended here. The first is that a manifest survives a
bare environment: every field it cannot observe is ``None`` and says so in
``unobserved``, because a benchmark that refused to start over a missing
``CHUNK_STRATEGY`` would be worse than one that admits it does not know.

The second is that the manifest never becomes an environment dump. The
secret-leak tests populate the environment with the credential shapes this
repository actually deploys — broker URLs with inline passwords, the internal
auth secret, a LangSmith API key — and assert none of their values reach the
serialized document by any path.
"""
from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from app.core.config import RAGConfig
from app.services.benchmark_manifest import (
    MANIFEST_VERSION,
    MAX_ENV_VALUE_CHARS,
    ManifestAllowlistError,
    _assert_safe_name,
    build_benchmark_manifest,
)

# Assembled at runtime so the tracked source never carries a complete
# private-key header, which the public-repo secret scanner rightly rejects.
FAKE_PRIVATE_KEY_HEADER = "-----" + "BEGIN " + "PRIVATE " + "KEY" + "-----"

# Values no manifest may ever contain, under env names a careless "capture
# everything" implementation would happily copy.
SECRET_ENV = {
    "RABBITMQ_URL": "amqp://admin:hunter2@rabbit:5672/",
    "MONGODB_URL": "mongodb://root:s3cr3t@mongo:27017/",
    "INTERNAL_AUTH_SECRET": "internal-auth-please-do-not-log",
    "LANGSMITH_API_KEY": "ls__abcdefghijklmnop",
    "OPENAI_API_KEY": "sk-livekeyvalue",
    "JWT_PRIVATE_KEY": FAKE_PRIVATE_KEY_HEADER,
}

BUILD_ENV = {
    "RAGFORGE_GIT_SHA": "1f2e3d4c5b6a7988",
    "RAGFORGE_GIT_BRANCH": "feat/benchmark-run-manifest",
    "RAGFORGE_BUILD_TIMESTAMP": "2026-08-26T12:00:00Z",
}

DATASET = {
    "dataset_id": "ds-1",
    "dataset_version": 3,
    "dataset_sha256": "a" * 64,
    "name": "Golden set",
}


@pytest.fixture
def config() -> RAGConfig:
    return RAGConfig()


def manifest_text(manifest: Dict[str, Any]) -> str:
    """The manifest exactly as it travels — a leak anywhere in it fails."""
    return json.dumps(manifest, default=str)


TOKEN_BUDGET_ENV = {
    "ANSWER_GENERATION_MAX_TOKENS": "128",
    "ANSWER_EVALUATION_MAX_TOKENS": "512",
    "CONTENT_RISK_SCAN_MAX_TOKENS": "128",
    "QUERY_REWRITE_MAX_TOKENS": "128",
    "MEMORY_EXTRACTION_MAX_TOKENS": "512",
}


# ── Missing values ────────────────────────────────────────────────────────

def test_a_bare_environment_serializes_with_nulls_not_guesses(config):
    """Nothing injected: every uncapturable field is null and named."""
    manifest = build_benchmark_manifest(config, env={})

    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["build"]["git_sha"] is None
    assert manifest["embedding"]["model"] is None
    assert manifest["chunking"]["strategy"] is None
    assert manifest["llm"]["chat_model"] is None
    assert manifest["llm"]["max_tokens"] == {
        "answer_generation": None,
        "answer_evaluation": None,
        "content_risk_scan": None,
        "query_rewrite": None,
        "memory_extraction": None,
    }
    for path in (
        "build.git_sha",
        "build.git_branch",
        "build.build_timestamp",
        "embedding.model",
        "chunking.strategy",
        "chunking.size",
        "vector_store.collection",
        "llm.chat_model",
        "llm.max_tokens.answer_generation",
    ):
        assert path in manifest["unobserved"]
    # Serializable as-is: a manifest that only survives a populated
    # environment is not a manifest.
    assert json.loads(manifest_text(manifest))["unobserved"]


def test_what_rag_can_observe_is_never_reported_as_unknown(config):
    """Retrieval settings come from live config, so they are always captured."""
    manifest = build_benchmark_manifest(config, env={})

    assert manifest["retrieval"]["top_k_documents"] == config.top_k_documents
    assert manifest["retrieval"]["eval_candidate_k"] == config.eval_candidate_k
    # Including the effective fields whose value is a null finding: "no
    # reranker model" is something the manifest knows, not something it
    # failed to capture.
    assert not [
        path for path in manifest["unobserved"] if path.startswith("retrieval.")
    ]
    assert manifest["software"]["python_version"]
    assert manifest["build"]["service"] == config.service_name


def test_a_dataset_is_recorded_by_version_and_fingerprint(config):
    """The id alone cannot prove two benchmarks scored the same labels."""
    manifest = build_benchmark_manifest(
        config,
        dataset=DATASET,
        item_count=12,
        phases=["retrieval_base", "end_to_end_regular"],
        env={},
    )

    assert manifest["dataset"]["dataset_id"] == "ds-1"
    assert manifest["dataset"]["dataset_version"] == 3
    assert manifest["dataset"]["dataset_sha256"] == "a" * 64
    assert manifest["dataset"]["item_count"] == 12
    assert manifest["dataset"]["phases"] == ["retrieval_base", "end_to_end_regular"]
    assert "dataset.dataset_id" not in manifest["unobserved"]


def test_a_benchmark_without_a_dataset_document_still_serializes(config):
    """The dataset section degrades to nulls rather than raising."""
    manifest = build_benchmark_manifest(config, env={})

    assert manifest["dataset"]["dataset_id"] is None
    assert "dataset.dataset_sha256" in manifest["unobserved"]


# ── Injected build identity ───────────────────────────────────────────────

def test_injected_build_identity_is_captured(config):
    """The container has no checkout; the image stamps these at build time."""
    manifest = build_benchmark_manifest(config, env=dict(BUILD_ENV))

    assert manifest["build"]["git_sha"] == BUILD_ENV["RAGFORGE_GIT_SHA"]
    assert manifest["build"]["git_branch"] == "feat/benchmark-run-manifest"
    assert manifest["build"]["build_timestamp"] == "2026-08-26T12:00:00Z"
    # An image tag is optional; it is the only build field left unknown.
    assert [
        path for path in manifest["unobserved"] if path.startswith("build.")
    ] == ["build.image_tag"]


def test_the_ragforge_name_wins_over_the_generic_ci_one(config):
    """Both are accepted, but the image's own stamp is the authority."""
    manifest = build_benchmark_manifest(
        config, env={"RAGFORGE_GIT_SHA": "ragforge-sha", "GIT_SHA": "ci-sha"}
    )

    assert manifest["build"]["git_sha"] == "ragforge-sha"


def test_a_generic_ci_name_is_used_when_nothing_ragforge_is_set(config):
    manifest = build_benchmark_manifest(config, env={"GIT_COMMIT": "ci-sha"})

    assert manifest["build"]["git_sha"] == "ci-sha"


def test_model_and_corpus_metadata_come_from_the_deployment(config):
    manifest = build_benchmark_manifest(
        config,
        env={
            "EMBEDDING_MODEL": "BAAI/bge-m3",
            "VECTOR_DB_VECTOR_SIZE": "1024",
            "VECTOR_DB_COLLECTION_NAME": "documents",
            "VECTOR_STORE_TYPE": "qdrant",
            "CHUNK_STRATEGY": "recursive",
            "CHUNK_SIZE": "800",
            "CHUNK_OVERLAP": "120",
            "LLM_IMPLEMENTATION": "vllm",
            "RAG_CHAT_MODEL": "RedHatAI/Qwen3.5-4B-quantized.w4a16",
            "VLLM_MAX_MODEL_LEN": "4096",
            "VLLM_MAX_NUM_SEQS": "3",
            "VLLM_QUANTIZATION": "compressed-tensors",
            **TOKEN_BUDGET_ENV,
        },
    )

    assert manifest["embedding"] == {"model": "BAAI/bge-m3", "vector_size": 1024}
    assert manifest["chunking"] == {
        "strategy": "recursive",
        "size": 800,
        "overlap": 120,
    }
    assert manifest["vector_store"] == {"collection": "documents", "type": "qdrant"}
    assert manifest["llm"]["chat_model"].startswith("RedHatAI/")
    assert manifest["llm"]["max_model_len"] == 4096
    assert manifest["llm"]["max_num_seqs"] == 3
    assert manifest["llm"]["quantization"] == "compressed-tensors"
    assert manifest["llm"]["max_tokens"] == {
        "answer_generation": 128,
        "answer_evaluation": 512,
        "content_risk_scan": 128,
        "query_rewrite": 128,
        "memory_extraction": 512,
    }
    assert [
        path
        for path in manifest["unobserved"]
        if path.split(".")[0] in {"embedding", "chunking", "vector_store", "llm"}
    ] == []


def test_a_value_that_will_not_coerce_is_unknown_not_text(config):
    """A chunk size of "large" compares equal to nothing; null says so."""
    manifest = build_benchmark_manifest(
        config, env={"CHUNK_SIZE": "large", "CHUNK_OVERLAP": " 120 "}
    )

    assert manifest["chunking"]["size"] is None
    assert manifest["chunking"]["overlap"] == 120
    assert "chunking.size" in manifest["unobserved"]


def test_invalid_max_num_seqs_is_not_recorded_as_effective(config):
    manifest = build_benchmark_manifest(
        config, env={"VLLM_MAX_NUM_SEQS": "not-an-integer"}
    )

    assert manifest["llm"]["max_num_seqs"] is None
    assert "llm.max_num_seqs" in manifest["unobserved"]


def test_invalid_action_budget_is_unknown_not_assumed(config):
    manifest = build_benchmark_manifest(
        config, env={**TOKEN_BUDGET_ENV, "QUERY_REWRITE_MAX_TOKENS": "invalid"}
    )

    assert manifest["llm"]["max_tokens"]["query_rewrite"] is None
    assert "llm.max_tokens.query_rewrite" in manifest["unobserved"]


def test_an_oversized_value_is_dropped_rather_than_stored(config):
    """A manifest is provenance, not a place to park a payload."""
    manifest = build_benchmark_manifest(
        config, env={"EMBEDDING_MODEL": "x" * (MAX_ENV_VALUE_CHARS + 1)}
    )

    assert manifest["embedding"]["model"] is None
    assert "embedding.model" in manifest["unobserved"]


# ── Secret leaks ──────────────────────────────────────────────────────────

def test_no_secret_in_the_environment_reaches_the_manifest(config):
    """The regression this module exists to prevent."""
    env = {**SECRET_ENV, **BUILD_ENV, "EMBEDDING_MODEL": "BAAI/bge-m3"}

    text = manifest_text(build_benchmark_manifest(config, dataset=DATASET, env=env))

    for name, value in SECRET_ENV.items():
        assert value not in text, f"{name} leaked into the manifest"
        assert name not in text


def test_the_manifest_does_not_carry_secret_config_fields(config):
    """`RAGConfig` holds credentials too, so the config side is allowlisted."""
    text = manifest_text(build_benchmark_manifest(config, env={}))

    assert config.internal_auth_secret not in text
    assert config.mongodb_url not in text
    assert config.rabbitmq_url not in text


def test_the_process_environment_is_never_swept(config, monkeypatch):
    """Default construction reads named variables, not everything present."""
    monkeypatch.setenv("A_TOTALLY_UNRELATED_VARIABLE", "leak-me-please")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "process-level-secret")
    monkeypatch.setenv("RAGFORGE_GIT_SHA", "sha-from-process-env")

    manifest = build_benchmark_manifest(config)

    text = manifest_text(manifest)
    assert manifest["build"]["git_sha"] == "sha-from-process-env"
    assert "leak-me-please" not in text
    assert "process-level-secret" not in text


@pytest.mark.parametrize(
    "name",
    [
        "LANGSMITH_API_KEY",
        "INTERNAL_AUTH_SECRET",
        "MONGODB_URL",
        "SOME_TOKEN",
        "DB_PASSWORD",
        "JWT_PRIVATE_KEY",
    ],
)
def test_a_credential_shaped_name_cannot_be_allowlisted(name):
    """The guard fires on the edit that adds the leak, not in production."""
    with pytest.raises(ManifestAllowlistError):
        _assert_safe_name(name)


def test_the_shipped_allowlist_passes_its_own_guard():
    """Import-time enforcement, restated so a regression names itself."""
    from app.services.benchmark_manifest import _ENV_FIELDS, _LLM_MAX_TOKEN_ENV_FIELDS

    for section in (*_ENV_FIELDS.values(), _LLM_MAX_TOKEN_ENV_FIELDS):
        for names, _kind in section.values():
            for name in names:
                assert _assert_safe_name(name) == name


def test_the_retrieval_section_reports_what_runs_not_the_legacy_flags(config):
    """`RAGConfig` defaults `reranker_enabled` and `hybrid_search_enabled` to
    true and no retrieval code reads either. A manifest that copied them
    would attribute a benchmark's numbers to a reranker and a hybrid
    retriever that were never in the request path."""
    assert config.reranker_enabled is True
    assert config.hybrid_search_enabled is True

    retrieval = build_benchmark_manifest(config, env={})["retrieval"]

    assert retrieval["retrieval_strategy"] == "dense_vector"
    assert retrieval["hybrid_search_active"] is False
    assert retrieval["reranker_active"] is False
    assert retrieval["reranker_model"] is None
    # The legacy values are gone rather than recorded as inactive: a field
    # naming a stage that does not exist has no honest value.
    for legacy in (
        "reranker_enabled",
        "reranker_top_k",
        "hybrid_search_enabled",
        "hybrid_search_alpha",
        "min_similarity_threshold",
    ):
        assert legacy not in retrieval


def test_the_manifest_describes_the_pipeline_stages_a_benchmark_drives(config):
    """A manifest covers the deployed pipeline, which does run the graph, so
    its merge and pass-two settings are the production ones."""
    retrieval = build_benchmark_manifest(config, env={})["retrieval"]

    assert retrieval["reranker_implementation"] == "score_order_merge"
    assert retrieval["context_k"] == config.top_k_documents
    assert retrieval["merge_kept_k"] == config.top_k_documents * 2
    assert retrieval["pass_two_active"] is True
    assert retrieval["pass_two_score_threshold"] == config.pass_two_score_threshold
