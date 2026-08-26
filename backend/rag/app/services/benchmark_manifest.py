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
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.core.config import RAGConfig

# Bumped when the manifest's *shape* changes, so a stored manifest read back
# a year later can be interpreted under the rules it was written with. It is
# not a version for the values themselves — those are already self-describing
# through `unobserved`.
MANIFEST_VERSION = 1

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
    for token in _SECRET_NAME_TOKENS:
        if token in upper:
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
    },
}

# Config-sourced retrieval settings: the part of the pipeline rag *can*
# observe, so on a real `RAGConfig` none of these is ever unobserved. A field
# a future config drops is reported as unknown rather than crashing a
# benchmark, for the reason at the top of this module — the manifest is
# descriptive and must never be what stops a run. Listed by name rather than
# taken from a `model_dump()` for the allowlist reason above — `RAGConfig`
# also carries `internal_auth_secret` and `mongodb_url`.
_CONFIG_RETRIEVAL_FIELDS = (
    "top_k_documents",
    "min_similarity_threshold",
    "reranker_enabled",
    "reranker_top_k",
    "hybrid_search_enabled",
    "hybrid_search_alpha",
    "enable_retrieval_bypass",
    "pass_two_chunk_threshold",
    "pass_two_score_threshold",
    "eval_candidate_k",
    "eval_run_concurrency",
    "eval_validate_labels",
    "eval_stale_label_policy",
)

# Fail fast on an unsafe allowlist entry.
for _section_fields in _ENV_FIELDS.values():
    for _names, _kind in _section_fields.values():
        for _name in _names:
            _assert_safe_name(_name)


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
    return text


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
    """
    return sorted(
        f"{section}.{field}"
        for section, values in sections.items()
        for field, value in values.items()
        if value is None
    )


def build_benchmark_manifest(
    config: RAGConfig,
    *,
    dataset: Optional[Mapping[str, Any]] = None,
    item_count: Optional[int] = None,
    phases: Optional[List[str]] = None,
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
    build["service"] = getattr(config, "service_name", None)

    dataset_doc = dataset or {}
    dataset_section: Dict[str, Any] = {
        "dataset_id": dataset_doc.get("dataset_id"),
        "dataset_version": dataset_doc.get("dataset_version"),
        "dataset_sha256": dataset_doc.get("dataset_sha256"),
        "item_count": item_count,
        "phases": list(phases) if phases else None,
    }

    retrieval = {
        field: getattr(config, field, None) for field in _CONFIG_RETRIEVAL_FIELDS
    }

    software = {
        # Interpreter and OS only. Not `platform.node()`: a hostname
        # identifies a machine without telling a reader anything about why
        # two benchmarks differ.
        "python_version": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}".strip(),
        "implementation": sys.implementation.name,
    }

    sections: Dict[str, Dict[str, Any]] = {
        "build": build,
        "dataset": dataset_section,
        "retrieval": retrieval,
        "embedding": _env_section(_ENV_FIELDS["embedding"], environment),
        "chunking": _env_section(_ENV_FIELDS["chunking"], environment),
        "vector_store": _env_section(_ENV_FIELDS["vector_store"], environment),
        "llm": _env_section(_ENV_FIELDS["llm"], environment),
        "software": software,
    }

    return {
        "manifest_version": MANIFEST_VERSION,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        **sections,
        "unobserved": _unobserved_paths(sections),
    }
