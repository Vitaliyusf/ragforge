"""Reproducibility manifest for a benchmark run.

A benchmark number is only evidence if someone can say what produced it:
which build, which golden set, which retrieval settings, which embedding and
chunking and vector store, which LLM. Asking an operator to write those down
by hand means they are remembered wrongly or not at all, so this module
captures them automatically at the moment a benchmark is planned.

Three rules hold everything together:

**An explicit allowlist, never a dump of the environment.** Every value in
the manifest comes from a named ``RAGConfig`` attribute or a named
environment variable listed in this module. ``os.environ`` is never iterated.
A process environment holds broker URLs, internal auth secrets and API keys,
and a manifest is read by every admin who opens a benchmark and travels into
any export made from one — the blast radius of "capture everything" is wrong
by default. Each allowlisted env name is additionally checked against
:data:`_SECRET_NAME_TOKENS` at import time, so a later edit adding
``LANGSMITH_API_KEY`` to the allowlist fails on import rather than in
production.

**Recorded is what runs, never what a legacy flag declares.** ``RAGConfig``
carries reranker and hybrid-search fields its own comment marks as legacy
compatibility flags, defaulted to true and read by no retrieval code. The
retrieval section takes those values from
:mod:`app.services.effective_retrieval` instead, so a benchmark cannot
attribute its numbers to a reranker or a hybrid retriever that was not in the
request path.

**Unknown is ``null``, never a guess.** rag cannot see the embedding model,
the chunk strategy or the LLM from inside its own process; it sees them only
when deployment injects them. A missing value is stored as ``None`` and its
dotted path is listed in ``unobserved``, exactly as
:func:`app.services.eval_store.build_config_snapshot` does and for the same
reason: two benchmarks run on *different* embedding models must not compare
as identical because both recorded ``None``.

**Build identity is injected, not inferred.** The container has no git
checkout, so ``RAGFORGE_GIT_SHA`` / ``RAGFORGE_GIT_BRANCH`` /
``RAGFORGE_BUILD_TIMESTAMP`` are stamped at image build time. Shelling out to
``git`` from a request path would be blocking I/O that reports the wrong
answer anyway.

The manifest is descriptive, not a contract the runner reads back: nothing in
the eval path branches on it, so a field that could not be captured degrades
the manifest and never the run.
"""
from __future__ import annotations

import os
import platform
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.core.config import RAGConfig
from app.services.effective_retrieval import (
    EFFECTIVE_RETRIEVAL_FIELDS,
    effective_retrieval_config,
)

# Bumped when the manifest's *shape* changes, so a stored manifest read back
# a year later can be interpreted under the rules it was written with. It is
# not a version for the values themselves — those are already self-describing
# through `unobserved`.
#
# Version 2 replaced the legacy `reranker_*` / `hybrid_search_*` /
# `min_similarity_threshold` values in the retrieval section with the
# effective ones. A stored version 1 manifest still reads back fine — nothing
# reads a manifest to drive behavior — but its retrieval section must be
# interpreted as config's declaration rather than as what ran.
# Version 3 adds the allowlisted LLM quantization used by the served runtime.
# Version 4 records the effective vLLM scheduler concurrency candidate.
# Version 5 records effective per-action output-token ceilings.
# Version 6 adds the `vllm` section: the served runtime's pinned version and
# every scheduler knob RAGForge sets or deliberately leaves to the server.
# Version 7 separates configured deployment intent from facts observed from
# the running server. Flat fields remain as compatibility aliases for older
# comparison/export readers; they are explicitly configuration-derived.
# Version 8 records the answer-evaluation structured-output transport and an
# observed vLLM version only when a runtime probe supplied one.
# Version 9 records the answer-evaluation output-schema fingerprint and the
# effective prompt version, so two runs scored under different judge contracts
# stop reading as identical.
# Version 10 records whether the built source tree was dirty and, when it was,
# a deterministic SHA-256 fingerprint of that tree. The commit SHA alone is
# not a source identity for a dirty build.
MANIFEST_VERSION = 10

# Longest env value copied into a manifest. A model identifier is tens of
# characters; anything far larger is a mistake or a payload, and neither
# belongs on a document every admin of the tenant can read.
MAX_ENV_VALUE_CHARS = 200

# Substrings that disqualify an environment variable from ever being
# allowlisted. Checked at import time against every name below, so the guard
# fires on the edit that introduces the leak rather than on the deployment
# that suffers it. `URL`/`URI`/`DSN` are included because this repository's
# connection strings carry inline credentials.
_SECRET_NAME_TOKENS = (
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "TOKEN",
    "KEY",
    "CREDENTIAL",
    "AUTH",
    "SALT",
    "PRIVATE",
    "URL",
    "URI",
    "DSN",
)


class ManifestAllowlistError(RuntimeError):
    """An environment name in the allowlist is not safe to capture."""


def _assert_safe_name(name: str) -> str:
    """Refuse an allowlist entry whose name marks it as a credential.

    Raises:
        ManifestAllowlistError: If the name contains a secret-shaped token.
    """
    upper = name.upper()
    # Plural TOKENS is a unit of work in these numeric provenance fields, not a
    # credential marker: ANSWER_GENERATION_MAX_TOKENS and
    # VLLM_MAX_NUM_BATCHED_TOKENS are integers. The singular TOKEN still
    # disqualifies, so HF_TOKEN and any VLLM_API_TOKEN remain refused. Values
    # are still allowlisted individually and numerically coerced.
    secret_shape = upper.replace("TOKENS", "")
    for token in _SECRET_NAME_TOKENS:
        if token in secret_shape:
            raise ManifestAllowlistError(
                f"Environment variable {name!r} may carry a credential and "
                "must not be captured in a benchmark manifest"
            )
    return name


# Environment-sourced fields, per section. Each entry maps a manifest field to
# the env names that may supply it, tried in order, plus the coercion applied
# to the raw string. The first name that yields a usable value wins; a value
# that will not coerce is treated as unobserved rather than stored as text,
# because a chunk size of "large" compares equal to nothing and unequal to
# everything.
_ENV_FIELDS: Dict[str, Dict[str, Tuple[Tuple[str, ...], str]]] = {
    "build": {
        # Both spellings are accepted: the RAGFORGE_-prefixed ones are what
        # this repository's images stamp, the bare ones are what most CI
        # systems already export, and accepting them costs nothing.
        "git_sha": (("RAGFORGE_GIT_SHA", "GIT_SHA", "GIT_COMMIT"), "str"),
        "git_branch": (("RAGFORGE_GIT_BRANCH", "GIT_BRANCH"), "str"),
        "git_dirty": (("RAGFORGE_GIT_DIRTY",), "bool"),
        "source_fingerprint_sha256": (
            ("RAGFORGE_SOURCE_FINGERPRINT_SHA256",),
            "str",
        ),
        "build_timestamp": (("RAGFORGE_BUILD_TIMESTAMP", "BUILD_TIMESTAMP"), "str"),
        "image_tag": (("RAGFORGE_IMAGE_TAG",), "str"),
    },
    "embedding": {
        # The same names `build_config_snapshot` reads, deliberately: a
        # manifest that disagreed with a run's own config snapshot about the
        # embedding model would make both unusable.
        "model": (("EMBEDDING_MODEL", "EMBEDDING_MODEL_NAME"), "str"),
        "vector_size": (("VECTOR_DB_VECTOR_SIZE",), "int"),
    },
    "chunking": {
        "strategy": (("CHUNK_STRATEGY",), "str"),
        "size": (("CHUNK_SIZE",), "int"),
        "overlap": (("CHUNK_OVERLAP",), "int"),
    },
    "vector_store": {
        "collection": (("VECTOR_DB_COLLECTION_NAME",), "str"),
        "type": (("VECTOR_STORE_TYPE",), "str"),
    },
    "llm": {
        "implementation": (("LLM_IMPLEMENTATION",), "str"),
        "chat_model": (("RAG_CHAT_MODEL",), "str"),
        "max_model_len": (("VLLM_MAX_MODEL_LEN",), "int"),
        "max_num_seqs": (("VLLM_MAX_NUM_SEQS",), "int"),
        "quantization": (("VLLM_QUANTIZATION",), "str"),
    },
    # The served runtime itself. Deployment injects each of these from the same
    # variable the `vllm` service is configured from, so the manifest cannot
    # describe a server other than the one that answered the benchmark.
    #
    # The scheduler knobs are listed even though RAGForge passes none of them
    # today. That is the point: a benchmark must be able to say "this run did
    # not set max_num_batched_tokens" and have a later tuned run compare as
    # different, rather than have both read as an absence nobody recorded.
    "vllm": {
        "image": (("VLLM_IMAGE",), "str"),
        "max_model_len": (("VLLM_MAX_MODEL_LEN",), "int"),
        "max_num_seqs": (("VLLM_MAX_NUM_SEQS",), "int"),
        "gpu_memory_utilization": (("VLLM_GPU_MEMORY_UTILIZATION",), "float"),
        "quantization": (("VLLM_QUANTIZATION",), "str"),
        "prefix_caching": (("VLLM_PREFIX_CACHING",), "bool"),
        "max_num_batched_tokens": (("VLLM_MAX_NUM_BATCHED_TOKENS",), "int"),
        "performance_mode": (("VLLM_PERFORMANCE_MODE",), "str"),
        "async_scheduling": (("VLLM_ASYNC_SCHEDULING",), "bool"),
        "chunked_prefill": (("VLLM_ENABLE_CHUNKED_PREFILL",), "bool"),
        "scheduler_reserve_full_isl": (("VLLM_SCHEDULER_RESERVE_FULL_ISL",), "bool"),
    },
}

# Scheduler knobs whose ``None`` means "RAGForge passes no flag; the server
# resolves its own value", not "nobody looked". They are exempt from
# ``unobserved`` for the same reason the effective-retrieval nulls are: the
# manifest is confident about them, and calling a proven non-configuration an
# unknown would leave two identically-unconfigured runs incomparable forever.
#
# What the *server* then resolved is a separate question this section does not
# answer and must not guess. Nothing here may be filled in from a release's
# documented defaults; the observed side lives in the run's Prometheus
# snapshot, which records what the running vLLM actually exported.
VLLM_UNCONFIGURED_FIELDS = frozenset({
    "max_num_batched_tokens",
    "performance_mode",
    "async_scheduling",
    "chunked_prefill",
    "scheduler_reserve_full_isl",
})

# An official version-pinned vLLM tag, e.g. `vllm/vllm-openai:v0.28.0`. A
# floating tag (`latest`, `nightly`, `main`) names no version, so it yields
# `None` rather than a version this module invented.
_PINNED_VLLM_TAG = re.compile(r"^v?(\d+\.\d+(?:\.\d+)?(?:\.?post\d+)?)$")

_LLM_MAX_TOKEN_ENV_FIELDS: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "answer_generation": (("ANSWER_GENERATION_MAX_TOKENS",), "int"),
    "answer_evaluation": (("ANSWER_EVALUATION_MAX_TOKENS",), "int"),
    "content_risk_scan": (("CONTENT_RISK_SCAN_MAX_TOKENS",), "int"),
    "query_rewrite": (("QUERY_REWRITE_MAX_TOKENS",), "int"),
    "memory_extraction": (("MEMORY_EXTRACTION_MAX_TOKENS",), "int"),
}

_ANSWER_EVALUATION_TRANSPORT_ENV = "ANSWER_EVALUATION_STRUCTURED_OUTPUT_TRANSPORT"
_OBSERVED_VLLM_VERSION_ENV = "VLLM_OBSERVED_SERVER_VERSION"

# The judge's contract, in two parts: the exact JSON Schema the evaluator was
# held to, and the prompt version that told it how to fill that schema in.
#
# Both are llm_agent facts, so rag receives them the way it receives the
# embedding model — injected by deployment, never inferred. rag has no route
# into llm_agent's Pydantic models and must not invent one from a request
# path. The schema value is a digest llm_agent computes from
# ``AnswerReviewParsedOutput.model_json_schema()``; it is generated by
# ``scripts/answer_review_schema_sha.py``, never typed by hand, because a
# hand-written digest would keep reading "unchanged" through exactly the edit
# it exists to catch.
#
# Missing means unknown. A manifest without these keys cannot prove that its
# benchmark was scored under the same judge contract as another, and the
# comparison says so rather than assuming they match: the GEN-03F cap on
# ``claims`` changed what the quality metrics measure, and two runs across
# that change must not compare as apples to apples.
_ANSWER_EVALUATION_SCHEMA_SHA_ENV = "ANSWER_EVALUATION_OUTPUT_SCHEMA_SHA256"
_ANSWER_EVALUATION_PROMPT_VERSION_ENV = "ANSWER_EVALUATION_PROMPT_VERSION"

_assert_safe_name(_ANSWER_EVALUATION_TRANSPORT_ENV)
_assert_safe_name(_OBSERVED_VLLM_VERSION_ENV)
_assert_safe_name(_ANSWER_EVALUATION_SCHEMA_SHA_ENV)
_assert_safe_name(_ANSWER_EVALUATION_PROMPT_VERSION_ENV)

# A SHA-256 hex digest and nothing else. Anything that is not one is not a
# fingerprint of a schema, so it is recorded as unknown rather than copied
# into the manifest as though it were provenance.
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

# ``<request_type>.v<N>``, the shape ``llm_agent``'s prompt registry uses. The
# pattern keeps a stray value out of the manifest for the same reason the
# digest pattern does, and keeps raw prompt *text* out of it by construction:
# nothing that is not a short version label can pass.
_PROMPT_VERSION = re.compile(r"^answer_evaluation\.v\d+$")

# Config-sourced retrieval settings: the part of the pipeline rag *can*
# observe, so on a real `RAGConfig` none of these is ever unobserved. A field
# a future config drops is reported as unknown rather than crashing a
# benchmark, for the reason at the top of this module — the manifest is
# descriptive and must never be what stops a run. Listed by name rather than
# taken from a `model_dump()` for the allowlist reason above — `RAGConfig`
# also carries `internal_auth_secret` and `mongodb_url`.
_CONFIG_RETRIEVAL_FIELDS = (
    "top_k_documents",
    "enable_retrieval_bypass",
    "eval_candidate_k",
    "eval_run_concurrency",
    "eval_validate_labels",
    "eval_stale_label_policy",
)

# The rest of the retrieval section describes what the pipeline *does*, not
# what config declares. Raw reranker/hybrid flags and
# `min_similarity_threshold` are deliberately
# absent from the raw allowlist above. Effective hybrid settings come from
# the live-path description below, while the unapplied similarity threshold
# remains excluded. The
# honest values come from `effective_retrieval_config`, whose own nulls are
# findings rather than gaps and are therefore exempt from `unobserved`. The
# manifest describes the deployed pipeline, which does run the conversation
# graph, so `pipeline_active` is true; a single eval run inside the benchmark
# records its own narrower answer in its `config_snapshot`.

# Fail fast on an unsafe allowlist entry.
for _section_fields in _ENV_FIELDS.values():
    for _names, _kind in _section_fields.values():
        for _name in _names:
            _assert_safe_name(_name)
for _names, _kind in _LLM_MAX_TOKEN_ENV_FIELDS.values():
    for _name in _names:
        _assert_safe_name(_name)


_TRUE_TEXT = frozenset({"1", "true", "yes", "on"})
_FALSE_TEXT = frozenset({"0", "false", "no", "off"})


def _coerce(raw: str, kind: str) -> Optional[Any]:
    """Convert one raw env string, or return ``None`` if it will not convert."""
    text = raw.strip()
    if not text or len(text) > MAX_ENV_VALUE_CHARS:
        return None
    if kind == "int":
        try:
            return int(text)
        except ValueError:
            return None
    if kind == "float":
        try:
            return float(text)
        except ValueError:
            return None
    if kind == "bool":
        lowered = text.lower()
        if lowered in _TRUE_TEXT:
            return True
        if lowered in _FALSE_TEXT:
            return False
        # Deliberately not `bool(text)`: a prefix-caching flag reading "maybe"
        # must come out unknown, never enabled.
        return None
    return text


def _pattern_value(raw: Optional[str], pattern: "re.Pattern[str]") -> Optional[str]:
    """Return ``raw`` only if it matches ``pattern``, else ``None``.

    A value the manifest cannot recognise is worth less than no value at all:
    recorded, it would make two runs compare as "different provenance" for a
    typo, or as "same" for two copies of the same wrong string. Unknown is the
    honest answer, and ``unobserved`` will say so.
    """
    value = _coerce(raw or "", "str")
    if value is None or not pattern.match(value):
        return None
    return value


def _vllm_server_version(image: Optional[str]) -> Optional[str]:
    """The vLLM version a pinned image tag names, or ``None`` if it names none.

    This is the version RAGForge deployed, read off the immutable tag it
    deployed. It is not a probe of the running process: rag has no route to the
    vLLM server, and a manifest built inside a request must not do blocking
    network I/O to find out. Recording it still matters, because the
    0.27.1-against-0.28.0 comparison this section exists for has to come out
    *incompatible* rather than unknown.
    """
    if not image:
        return None
    _, _, tag = image.rpartition(":")
    match = _PINNED_VLLM_TAG.match(tag)
    return match.group(1) if match else None


def _vllm_model_runner(raw: Optional[str]) -> Optional[str]:
    """Which model-runner generation the server was told to use.

    WSL2 cannot run the V2 runner, so which one a benchmark ran under is
    performance provenance rather than trivia. An unrecognised value stays
    unknown: guessing "v1" would silently certify a runner nobody verified.
    """
    enabled = _coerce(raw, "bool") if raw else None
    if enabled is None:
        return None
    return "v2" if enabled else "v1"


def _env_section(
    fields: Mapping[str, Tuple[Tuple[str, ...], str]],
    env: Mapping[str, str],
) -> Dict[str, Any]:
    """Resolve one section's fields from its allowlisted names only."""
    resolved: Dict[str, Any] = {}
    for field, (names, kind) in fields.items():
        value: Optional[Any] = None
        for name in names:
            raw = env.get(name)
            if raw:
                value = _coerce(raw, kind)
                if value is not None:
                    break
        resolved[field] = value
    return resolved


def _unobserved_paths(sections: Mapping[str, Mapping[str, Any]]) -> List[str]:
    """Dotted paths of every field the manifest could not capture.

    A reader must treat a path listed here as "not recorded" and refuse to
    call two benchmarks equal on it, the way a config diff does.

    The effective-retrieval fields are exempt because their nulls mean the
    opposite: "no reranker model exists", "no similarity floor is applied".
    Those are findings the manifest is confident about, and listing them as
    unseen would turn a proven absence back into an unknown — the same
    confusion, pointed the other way, that reporting a legacy flag as an
    active reranker created.
    """
    unobserved: List[str] = []

    def visit(path: str, value: Any) -> None:
        if isinstance(value, Mapping):
            for child, child_value in value.items():
                visit(f"{path}.{child}" if path else str(child), child_value)
        elif value is None:
            section, _, field = path.partition(".")
            nested_vllm_field = (
                path.removeprefix("vllm.configured.")
                if path.startswith("vllm.configured.")
                else ""
            )
            exempt = (
                section == "retrieval" and field in EFFECTIVE_RETRIEVAL_FIELDS
            ) or (section == "vllm" and field in VLLM_UNCONFIGURED_FIELDS)
            exempt = exempt or nested_vllm_field in VLLM_UNCONFIGURED_FIELDS
            # A clean tree needs no dirty-source digest. Its explicit false
            # dirty flag is the complete answer; only dirty builds require the
            # fingerprint that distinguishes modifications at the same SHA.
            exempt = exempt or (
                path == "build.source_fingerprint_sha256"
                and sections.get("build", {}).get("git_dirty") is False
            )
            if not exempt:
                unobserved.append(path)

    for section, values in sections.items():
        visit(section, values)
    return sorted(unobserved)


def build_benchmark_manifest(
    config: RAGConfig,
    *,
    dataset: Optional[Mapping[str, Any]] = None,
    item_count: Optional[int] = None,
    phases: Optional[List[str]] = None,
    requested_profile: Optional[str] = None,
    executable_phases: Optional[List[str]] = None,
    unsupported_phases: Optional[List[str]] = None,
    skipped_phases: Optional[List[str]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Capture what a benchmark is about to run under.

    Taken from live config and the process environment at plan time, never
    from the caller: a manifest the requester could supply would let two
    benchmarks claim the same provenance while running different code.

    Args:
        config: Live rag configuration.
        dataset: The dataset document being benchmarked, read for its id,
            version and fingerprint only. Those three together are what makes
            two benchmarks' labels comparable — the id alone cannot, because a
            dataset can be edited under a stable id.
        item_count: How many items the benchmark will score, supplied by the
            caller because it depends on the plan rather than on the stored
            dataset alone.
        phases: The phase names planned, recorded so a benchmark that ran two
            phases can be told from one that only ever intended two.
        env: Environment mapping to read, defaulting to ``os.environ``.
            Injected by tests; production never passes it.

    Returns:
        A JSON-safe manifest whose every unknown value is ``None`` and whose
        ``unobserved`` lists those values' dotted paths.
    """
    environment = os.environ if env is None else env

    build = _env_section(_ENV_FIELDS["build"], environment)
    build["source_fingerprint_sha256"] = _pattern_value(
        build.get("source_fingerprint_sha256"), _SHA256_HEX
    )
    build["service"] = getattr(config, "service_name", None)

    dataset_doc = dataset or {}
    dataset_section: Dict[str, Any] = {
        "dataset_id": dataset_doc.get("dataset_id"),
        "dataset_version": dataset_doc.get("dataset_version"),
        "dataset_sha256": dataset_doc.get("dataset_sha256"),
        "item_count": item_count,
        "phases": list(phases) if phases else None,
    }
    execution = {
        "requested_profile": requested_profile,
        "executable_phases": list(executable_phases or []),
        "unsupported_phases": list(unsupported_phases or []),
        "skipped_phases": list(skipped_phases or []),
    }

    retrieval = {
        field: getattr(config, field, None) for field in _CONFIG_RETRIEVAL_FIELDS
    }
    retrieval.update(effective_retrieval_config(config, pipeline_active=True))

    software = {
        # Interpreter and OS only. Not `platform.node()`: a hostname
        # identifies a machine without telling a reader anything about why
        # two benchmarks differ.
        "python_version": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}".strip(),
        "implementation": sys.implementation.name,
    }

    llm = _env_section(_ENV_FIELDS["llm"], environment)
    llm["max_tokens"] = _env_section(_LLM_MAX_TOKEN_ENV_FIELDS, environment)
    transport = _coerce(environment.get(_ANSWER_EVALUATION_TRANSPORT_ENV, ""), "str")
    llm["structured_output_transport"] = {
        "answer_evaluation": transport if transport in {"legacy", "json_schema"} else None
    }
    llm["output_schema_sha256"] = {
        "answer_evaluation": _pattern_value(
            environment.get(_ANSWER_EVALUATION_SCHEMA_SHA_ENV), _SHA256_HEX
        )
    }
    llm["prompt_version"] = {
        "answer_evaluation": _pattern_value(
            environment.get(_ANSWER_EVALUATION_PROMPT_VERSION_ENV), _PROMPT_VERSION
        )
    }

    configured_vllm = _env_section(_ENV_FIELDS["vllm"], environment)
    configured_vllm["server_version"] = _vllm_server_version(
        configured_vllm.get("image")
    )
    configured_vllm["model_runner"] = _vllm_model_runner(
        environment.get("VLLM_USE_V2_MODEL_RUNNER")
    )
    # These values cannot be observed safely from this synchronous request
    # path. The pre-benchmark warmup gate probes /version and /v1/models and
    # records those observations separately; no image tag is promoted into
    # this block as runtime proof.
    observed_vllm = {
        "server_version": _coerce(
            environment.get(_OBSERVED_VLLM_VERSION_ENV, ""), "str"
        ),
        "model_runner": None,
        "max_model_len": None,
    }
    vllm = {
        **configured_vllm,
        "configured": dict(configured_vllm),
        "observed": observed_vllm,
    }

    sections: Dict[str, Dict[str, Any]] = {
        "build": build,
        "dataset": dataset_section,
        "execution": execution,
        "retrieval": retrieval,
        "embedding": _env_section(_ENV_FIELDS["embedding"], environment),
        "chunking": _env_section(_ENV_FIELDS["chunking"], environment),
        "vector_store": _env_section(_ENV_FIELDS["vector_store"], environment),
        "llm": llm,
        "vllm": vllm,
        "software": software,
    }

    return {
        "manifest_version": MANIFEST_VERSION,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        **sections,
        "unobserved": _unobserved_paths(sections),
    }
