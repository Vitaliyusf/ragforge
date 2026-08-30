"""Provenance and resource sampling for a baseline run.

A latency number is only evidence if someone can say what produced it, so a
baseline artifact carries the build it measured, the hardware it ran on and
the config that was in force. This module collects those, and samples CPU/RAM
while a profile runs.

Every value here is best-effort and every failure degrades to ``None``. The
harness runs on a developer laptop, in CI, and against a Compose stack; a
provenance collector that raises because `git` is absent would make the
artifact impossible to produce exactly where it is most needed. What it will
not do is invent: an unknown CPU percentage is ``None``, never ``0.0``.

Config capture follows the same allowlist rule as
`app.services.benchmark_manifest`: named environment variables only,
``os.environ`` is never iterated, and every allowlisted name is checked
against a secret-token denylist at import time. An artifact is a file people
paste into pull requests.
"""
from __future__ import annotations

import importlib.util
import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:  # pragma: no cover - exercised by absence, not by branch
    import psutil

    _HAS_PSUTIL = True
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]
    _HAS_PSUTIL = False


# Concurrency-relevant configuration only. These are the knobs the whole
# `CONC-*` track moves, so a baseline that does not record them cannot be
# compared against anything.
#
# Every name here is a variable the running system actually reads: a Compose
# `${...}` substitution, or a pydantic/`os.getenv` field on a service config.
# A plausible-looking name that nothing reads is worse than an absent one — it
# records `null` for a knob that is in force, and a later comparison then
# calls two differently-configured runs identical. `test_conc_baseline_
# harness.py` re-derives the readable names from the repository and fails when
# the allowlist drifts away from them.
CONFIG_ALLOWLIST = (
    # vLLM scheduler: docker-compose.yml passes these to the server args and
    # re-exports them to the services that reason about the ceiling.
    "VLLM_MAX_NUM_SEQS",
    "VLLM_MAX_NUM_BATCHED_TOKENS",
    "VLLM_GPU_MEMORY_UTILIZATION",
    "VLLM_MODEL",
    "DEFAULT_MODEL",
    # LLM Agent concurrency. `MAX_CONCURRENT_REQUESTS` is unprefixed: the
    # service config declares `max_concurrent_requests` with no env prefix.
    "MAX_CONCURRENT_REQUESTS",
    # RabbitMQ prefetch. `RABBITMQ_PREFETCH_COUNT` is the shared consumer knob
    # every RPC service reads; `LLM_REQUEST_PREFETCH` is the separate prefetch
    # on llm_agent's primary typed request queue.
    "RABBITMQ_PREFETCH_COUNT",
    "LLM_REQUEST_PREFETCH",
    # Embedding batching.
    "EMBEDDING_BATCH_SIZE",
    "EMBEDDING_MAX_BATCH_SIZE",
    # Reranker. There is no worker-count knob today — the reranker's
    # concurrency is whatever the calling path grants it — so what the runtime
    # exposes is the forward-pass batch and the deadline. `CONC-05` adds a
    # concurrency setting; this list follows it then, not before.
    "RERANKER_ENABLED",
    "RERANKER_BATCH_SIZE",
    "RERANKER_TIMEOUT_SECONDS",
    # RAG background and persistence concurrency (unprefixed, as declared).
    "EVAL_RUN_CONCURRENCY",
    "PERSISTENCE_MAX_CONCURRENCY",
    "EXTENDED_RETRIEVAL_MAX_CONCURRENCY",
    # Kafka polling. `max_poll_records` is hard-coded to 1 in
    # `embedding_kafka.py` and so is not configuration; the poll deadline is.
    "KAFKA_CONSUMER_TIMEOUT_MS",
)


# A name with any of these as a whole underscore-delimited word must never
# reach an artifact. Matching whole words rather than substrings is what lets
# `VLLM_MAX_NUM_BATCHED_TOKENS` — a scheduler budget, and one of the most
# important knobs this track moves — through while still catching `HF_TOKEN`.
# The plural `TOKENS` is deliberately absent for that reason: in this
# repository a plural token name is always a model token count.
_SECRET_NAME_TOKENS = frozenset(
    {
        "SECRET",
        "SECRETS",
        "PASSWORD",
        "PASSWORDS",
        "TOKEN",
        "KEY",
        "KEYS",
        "APIKEY",
        "PEPPER",
        "CREDENTIAL",
        "CREDENTIALS",
    }
)


def _is_secret_shaped(name: str) -> bool:
    """True when any underscore-delimited word of `name` names a credential."""
    return bool(set(name.upper().split("_")) & _SECRET_NAME_TOKENS)


_offenders = [name for name in CONFIG_ALLOWLIST if _is_secret_shaped(name)]
if _offenders:  # pragma: no cover - import-time contract
    raise RuntimeError(
        f"CONFIG_ALLOWLIST contains secret-shaped names: {_offenders}. "
        "A baseline artifact is shared; it must never carry credentials."
    )


def utc_now_iso() -> str:
    """Timestamp for the artifact, in UTC with an explicit offset."""
    return datetime.now(timezone.utc).isoformat()


def _git_output(*args: str) -> Optional[str]:
    """Run a read-only git command.

    Returns the trimmed stdout — *including the empty string* — or ``None``
    when git could not answer at all. The distinction is the whole point for
    `git status --porcelain`, where empty output is the answer "clean" and
    collapsing it into ``None`` would report every clean tree as unknown.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git(*args: str) -> Optional[str]:
    """`_git_output` for the commands where empty output carries no meaning."""
    return _git_output(*args) or None


def source_fingerprint() -> Dict[str, Optional[object]]:
    """Identify the source tree that produced this baseline, reproducibly.

    ``dirty`` matters more than the SHA: a baseline recorded from a working
    tree with uncommitted changes cannot be reproduced from the SHA alone, and
    a later comparison against it would silently attribute the difference to
    the wrong change. Recording ``dirty: true`` and stopping there states the
    problem without giving a reader anything to do about it — two runs from
    two different dirty trees still look identical.

    So a dirty tree also carries ``source_fingerprint_sha256``: the same
    content-addressed identity the RAG image build stamps into its provenance,
    reused from :func:`scripts.build_rag_image.dirty_source_fingerprint` rather
    than reimplemented, so an artifact and an image built from the same tree
    agree on what "this source" means. It hashes the tracked diff against
    ``HEAD`` plus every non-ignored untracked path and its content, so it moves
    whenever the source moves and is stable when the source is not. It is a
    digest: no diff, no file content and no path list survives into the
    artifact.

    On a clean tree the SHA *is* the identity, so the fingerprint is ``None``
    rather than a hash of an empty diff — a value that would be constant
    across every clean run and could be mistaken for a real reading.
    """
    status = _git_output("status", "--porcelain=v1", "--untracked-files=all")
    git_sha = _git("rev-parse", "HEAD")
    dirty = None if status is None else bool(status)

    fingerprint: Optional[str] = None
    if dirty and git_sha is not None:
        fingerprint = _dirty_fingerprint(git_sha)

    return {
        "git_sha": git_sha,
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": dirty,
        "source_fingerprint_sha256": fingerprint,
    }


_BUILD_SCRIPT = Path(__file__).resolve().parents[1] / "build_rag_image.py"


def _dirty_fingerprint(git_sha: str) -> Optional[str]:
    """The shared dirty-source digest, or ``None`` if it cannot be computed.

    Loaded from its file rather than imported by name: `scripts/` is not a
    package, so the sibling module is only importable when a caller has
    already put `scripts/` on `sys.path`, and the harness must not depend on
    that. Everything still degrades to ``None`` — an artifact from a tree with
    no git is worth less, but it is still worth writing.
    """
    try:
        spec = importlib.util.spec_from_file_location("_perf_build_provenance", _BUILD_SCRIPT)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return str(module.dirty_source_fingerprint(git_sha))
    except (OSError, AttributeError, subprocess.SubprocessError):
        return None


def config_snapshot() -> Dict[str, Optional[str]]:
    """Allowlisted concurrency configuration, unset names recorded as ``None``."""
    return {name: os.environ.get(name) for name in CONFIG_ALLOWLIST}


def hardware_runtime() -> Dict[str, Optional[object]]:
    """Machine and interpreter the harness itself ran on."""
    logical = os.cpu_count()
    total_ram = None
    if _HAS_PSUTIL:
        try:
            total_ram = psutil.virtual_memory().total
        except Exception:  # pragma: no cover - platform dependent
            total_ram = None
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": sys.version.split()[0],
        "logical_cpus": logical,
        "total_ram_bytes": total_ram,
        # Stated so a reader knows the CPU/RAM figures describe the harness
        # host, which is only the system under test when both run here.
        "resource_sampling_available": _HAS_PSUTIL,
    }


@dataclass(frozen=True)
class ResourceSample:
    """One CPU/RAM reading. ``None`` means unmeasured, never idle."""

    cpu_percent: Optional[float]
    ram_used_bytes: Optional[int]


class ResourceSampler:
    """Sample host CPU/RAM on a background thread while a profile runs.

    A thread rather than a loop callback on purpose: the harness drives load on
    an event loop, and sampling from that same loop would make the measurement
    compete with the thing being measured — the sampler would report low lag
    exactly when the loop was busiest.

    With psutil absent the sampler still starts and still stops; it simply
    collects nothing and the artifact records ``None``.
    """

    def __init__(self, interval: float = 0.5) -> None:
        self._interval = interval
        self._samples: List[ResourceSample] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def __enter__(self) -> "ResourceSampler":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def start(self) -> None:
        if not _HAS_PSUTIL or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="perf-resource-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=self._interval * 4)

    def _run(self) -> None:  # pragma: no cover - timing-dependent thread body
        while not self._stop.is_set():
            try:
                self._samples.append(
                    ResourceSample(
                        cpu_percent=psutil.cpu_percent(interval=None),
                        ram_used_bytes=psutil.virtual_memory().used,
                    )
                )
            except Exception:
                self._samples.append(ResourceSample(cpu_percent=None, ram_used_bytes=None))
            self._stop.wait(self._interval)

    def summary(self) -> Dict[str, Optional[float]]:
        """Mean/peak of what was actually collected."""
        cpu = [s.cpu_percent for s in self._samples if s.cpu_percent is not None]
        ram = [s.ram_used_bytes for s in self._samples if s.ram_used_bytes is not None]
        return {
            "samples": len(self._samples),
            "cpu_percent_mean": (sum(cpu) / len(cpu)) if cpu else None,
            "cpu_percent_peak": max(cpu) if cpu else None,
            "ram_used_bytes_mean": (sum(ram) / len(ram)) if ram else None,
            "ram_used_bytes_peak": max(ram) if ram else None,
        }


def resource_limitations() -> List[str]:
    """Limitations the current host imposes on resource figures."""
    if not _HAS_PSUTIL:
        return [
            "CPU/RAM not measured: psutil is unavailable in this environment, "
            "so those fields are null rather than zero"
        ]
    return []


def monotonic() -> float:
    """Single clock source for the harness, so durations never go backwards."""
    return time.perf_counter()
