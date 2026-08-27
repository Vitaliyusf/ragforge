"""Readiness gate, startup evidence and warm-up for the vLLM server.

Run this once against the vLLM container before *every* measured benchmark,
under every version being compared. Two different things go wrong without it,
and they look the same in the results:

* The container process exists long before the OpenAI server does. Weights
  load, kernels compile, CUDA graphs are captured; requests sent during that
  window fail or stall, and the first benchmark items absorb the cost of a
  cold start that has nothing to do with the configuration under test.
* Even after ``/health`` answers, the first real generation pays one-time
  JIT and graph costs. Measuring that request as though it were a steady-state
  one attributes a startup artifact to whichever version happened to run first.

So: wait for health, prove the model is actually served, spend one tiny bounded
generation, and only then start the benchmark. The warm-up request is never
scored — it does not go through the benchmark path at all.

The script also prints the startup evidence block a version comparison needs.
Everything it reports is **observed from the running server**. A value the
server does not expose is printed as ``"unobserved"``; nothing is ever filled
in from a release's documented defaults, because a scheduler default that was
assumed rather than seen is exactly the evidence an upgrade experiment cannot
use.

Usage, from the repository root::

    docker compose exec -T -e WARMUP_API_KEY="$VLLM_API_KEY" vllm python3 - \\
        < scripts/vllm_warmup.py

It runs *inside* the container deliberately: vLLM is reachable only on the
internal ``ai`` network, and warming it up is not a reason to publish its port
to the host. Only stdlib is imported, so it runs in the vLLM image as shipped.

Exit status is 0 when the server is ready and the warm-up succeeded, and 1
otherwise — a non-zero exit means do not start the benchmark yet.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

BASE_URL = os.environ.get("WARMUP_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("WARMUP_API_KEY", "")
READY_TIMEOUT_SECONDS = float(os.environ.get("WARMUP_READY_TIMEOUT", "1800"))
POLL_SECONDS = 5.0
REQUEST_TIMEOUT_SECONDS = 30.0

UNOBSERVED = "unobserved"

# Resolved-configuration fields worth reporting, and the label vLLM publishes
# them under in `vllm:cache_config_info`. Names differ across releases, so a
# field is reported only when the running server actually labelled it.
_CACHE_INFO_FIELDS = (
    "block_size",
    "num_gpu_blocks",
    "num_gpu_blocks_override",
    "gpu_memory_utilization",
    "enable_prefix_caching",
    "cache_dtype",
    "sliding_window",
)


def _request(
    path: str, *, payload: Optional[Dict[str, Any]] = None, timeout: float
) -> Any:
    """One JSON call against the server, or ``None`` if it did not answer."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    # /health, /metrics and /version are exempt from --api-key; /v1/* is not.
    if API_KEY and path.startswith("/v1"):
        headers["Authorization"] = f"Bearer {API_KEY}"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    if not body:
        return {}
    try:
        return json.loads(body)
    except ValueError:
        return body


def _text(path: str, *, timeout: float) -> Optional[str]:
    """Fetch a non-JSON endpoint (``/metrics``) as text."""
    result = _request(path, timeout=timeout)
    return result if isinstance(result, str) else None


def wait_for_health() -> bool:
    """Poll ``/health`` until the OpenAI server answers, or give up.

    A long deadline is correct here: a cold weight download plus graph capture
    genuinely takes many minutes, and failing early would only push that cost
    into the benchmark's first items.
    """
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while True:
        url = f"{BASE_URL}/health"
        try:
            with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as reply:
                if reply.status == 200:
                    return True
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)


def served_models() -> List[str]:
    """Model ids the server says it is serving, from ``/v1/models``."""
    body = _request("/v1/models", timeout=REQUEST_TIMEOUT_SECONDS)
    if not isinstance(body, dict):
        return []
    return [
        str(entry.get("id"))
        for entry in body.get("data") or []
        if isinstance(entry, dict) and entry.get("id")
    ]


def server_version() -> Any:
    """The version the process reports, if this release exposes ``/version``."""
    body = _request("/version", timeout=REQUEST_TIMEOUT_SECONDS)
    if isinstance(body, dict) and body.get("version"):
        return str(body["version"])
    return UNOBSERVED


def _parse_labels(sample: str) -> Dict[str, str]:
    """Labels of one Prometheus sample line, ignoring what does not parse."""
    start, end = sample.find("{"), sample.rfind("}")
    if start < 0 or end < start:
        return {}
    labels: Dict[str, str] = {}
    for part in sample[start + 1 : end].split('",'):
        name, _, value = part.partition("=")
        name = name.strip()
        value = value.strip().strip('"')
        if name:
            labels[name] = value
    return labels


def resolved_cache_config() -> Dict[str, Any]:
    """Whatever the running server published about its resolved cache config.

    Read from ``vllm:cache_config_info`` on ``/metrics`` rather than from the
    flags this deployment believes it passed. A label the release does not
    publish stays ``unobserved``; nothing here is inferred.
    """
    metrics = _text("/metrics", timeout=REQUEST_TIMEOUT_SECONDS)
    resolved: Dict[str, Any] = {field: UNOBSERVED for field in _CACHE_INFO_FIELDS}
    if not metrics:
        return resolved
    for line in metrics.splitlines():
        if not line.startswith("vllm:cache_config_info"):
            continue
        labels = _parse_labels(line)
        for field in _CACHE_INFO_FIELDS:
            if field in labels:
                resolved[field] = labels[field]
        break
    return resolved


def exported_metric_names() -> Any:
    """Which ``vllm:`` metric families the running server actually exports.

    Printed so a benchmark reader can tell "this release does not export
    preemption counters" from "no preemptions happened" — the two are
    indistinguishable in an empty query result, and only one of them is news.
    """
    metrics = _text("/metrics", timeout=REQUEST_TIMEOUT_SECONDS)
    if not metrics:
        return UNOBSERVED
    names = {
        line.split()[1]
        for line in metrics.splitlines()
        if line.startswith("# TYPE ") and len(line.split()) > 2
    }
    return sorted(name for name in names if name.startswith("vllm:"))


def warm_up(model: str) -> Dict[str, Any]:
    """Spend one tiny bounded generation so the benchmark does not.

    ``max_tokens=1`` and a two-word prompt: enough to force the first real
    forward pass through the served graph, small enough that it cannot
    meaningfully move the token counters the benchmark reads afterwards.
    """
    started = time.monotonic()
    body = _request(
        "/v1/chat/completions",
        payload={
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
            "stream": False,
        },
        timeout=max(REQUEST_TIMEOUT_SECONDS, 120.0),
    )
    elapsed_ms = round((time.monotonic() - started) * 1000.0, 1)
    ok = isinstance(body, dict) and bool(body.get("choices"))
    return {"ok": ok, "elapsed_ms": elapsed_ms if ok else None}


def main() -> int:
    evidence: Dict[str, Any] = {"base_url": BASE_URL}

    evidence["health"] = "ready" if wait_for_health() else "not_ready"
    if evidence["health"] != "ready":
        evidence["warmup"] = {"ok": False, "elapsed_ms": None}
        evidence["error"] = "vLLM did not become healthy within the deadline"
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 1

    models = served_models()
    evidence["server_version"] = server_version()
    evidence["models"] = models or UNOBSERVED
    evidence["resolved_cache_config"] = resolved_cache_config()
    evidence["exported_vllm_metrics"] = exported_metric_names()

    if not models:
        evidence["warmup"] = {"ok": False, "elapsed_ms": None}
        evidence["error"] = "server is healthy but reports no served model"
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 1

    evidence["warmup"] = warm_up(models[0])
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["warmup"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
