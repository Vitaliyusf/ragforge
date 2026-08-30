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

import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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
CONFIG_ALLOWLIST = (
    "VLLM_MAX_NUM_SEQS",
    "VLLM_GPU_MEMORY_UTILIZATION",
    "VLLM_MAX_NUM_BATCHED_TOKENS",
    "VLLM_MODEL",
    "DEFAULT_MODEL",
    "LLM_MAX_CONCURRENT_REQUESTS",
    "LLM_RABBITMQ_PREFETCH",
    "EMBEDDING_RABBITMQ_PREFETCH",
    "EMBEDDING_BATCH_SIZE",
    "RERANKER_MAX_WORKERS",
    "EVAL_RUN_CONCURRENCY",
    "RAG_PERSISTENCE_MAX_CONCURRENCY",
    "UVICORN_WORKERS",
    "KAFKA_MAX_RECORDS",
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


def _git(*args: str) -> Optional[str]:
    """Run a read-only git command, or return ``None`` if git cannot answer."""
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
    return result.stdout.strip() or None


def source_fingerprint() -> Dict[str, Optional[object]]:
    """Identify the source tree that produced this baseline.

    ``dirty`` matters more than the SHA: a baseline recorded from a working
    tree with uncommitted changes cannot be reproduced from the SHA alone, and
    a later comparison against it would silently attribute the difference to
    the wrong change.
    """
    status = _git("status", "--porcelain")
    return {
        "git_sha": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": None if status is None else bool(status),
    }


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
