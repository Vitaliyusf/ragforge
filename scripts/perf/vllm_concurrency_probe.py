"""Small, fixed-shape CONC-03 capacity probe for a running vLLM server."""
from __future__ import annotations

import concurrent.futures
import json
import math
import os
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


BASE_URL = os.environ.get("PROBE_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("PROBE_API_KEY", "")
CONCURRENCY_LEVELS = (1, 2, 4, 8)
REQUESTS_PER_LEVEL = 8
MAX_TOKENS = 64
TIMEOUT_SECONDS = 180.0
PROMPT = (
    "Write a compact numbered list of practical steps for validating a software "
    "change. Continue until the response reaches the available output budget."
    "\n\nAssistant:\n<think>\n\n</think>\n\n"
)


def _json_request(path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if API_KEY and path.startswith("/v1"):
        headers["Authorization"] = f"Bearer {API_KEY}"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode())


def _model() -> str:
    body = _json_request("/v1/models")
    return str(body["data"][0]["id"])


def _percentile(values: List[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 4)


def _gpu_sample() -> Optional[Dict[str, float]]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
        utilization, used, total = result.stdout.splitlines()[0].split(",")
        return {
            "utilization_percent": float(utilization.strip()),
            "memory_used_mib": float(used.strip()),
            "memory_total_mib": float(total.strip()),
        }
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return None


def _completion(model: str, active: Dict[str, int], lock: threading.Lock) -> Dict[str, Any]:
    started = time.perf_counter()
    ttft = None
    usage: Dict[str, int] = {}
    request = urllib.request.Request(
        f"{BASE_URL}/v1/completions",
        data=json.dumps(
            {
                "model": model,
                "prompt": PROMPT,
                "max_tokens": MAX_TOKENS,
                "temperature": 0.0,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
        ).encode(),
        headers={
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    with lock:
        active["current"] += 1
        active["maximum"] = max(active["maximum"], active["current"])
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                choices = chunk.get("choices") or []
                if ttft is None and choices and choices[0].get("text"):
                    ttft = time.perf_counter() - started
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]
        return {
            "e2e": time.perf_counter() - started,
            "ttft": ttft,
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "error": None,
        }
    except TimeoutError as exc:
        return {"error": type(exc).__name__, "timeout": True}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"error": type(exc).__name__, "timeout": False}
    finally:
        with lock:
            active["current"] -= 1


def _run_level(model: str, concurrency: int) -> Dict[str, Any]:
    active = {"current": 0, "maximum": 0}
    active_lock = threading.Lock()
    stop_sampling = threading.Event()
    gpu_samples: List[Dict[str, float]] = []

    def sample_gpu() -> None:
        while not stop_sampling.is_set():
            sample = _gpu_sample()
            if sample is not None:
                gpu_samples.append(sample)
            stop_sampling.wait(0.1)

    sampler = threading.Thread(target=sample_gpu, daemon=True)
    sampler.start()
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(
            executor.map(
                lambda _index: _completion(model, active, active_lock),
                range(REQUESTS_PER_LEVEL),
            )
        )
    elapsed = time.perf_counter() - started
    stop_sampling.set()
    sampler.join(2.0)

    successful = [result for result in results if result.get("error") is None]
    e2e = [result["e2e"] for result in successful]
    ttft = [result["ttft"] for result in successful if result.get("ttft") is not None]
    output_tokens = sum(result.get("output_tokens") or 0 for result in successful)
    input_tokens = sum(result.get("input_tokens") or 0 for result in successful)
    timeouts = sum(bool(result.get("timeout")) for result in results)
    return {
        "concurrency": concurrency,
        "requests": REQUESTS_PER_LEVEL,
        "achieved_concurrency": active["maximum"],
        "rps": round(len(successful) / elapsed, 4),
        "e2e_p50_seconds": _percentile(e2e, 0.50),
        "e2e_p95_seconds": _percentile(e2e, 0.95),
        "ttft_p50_seconds": _percentile(ttft, 0.50),
        "ttft_p95_seconds": _percentile(ttft, 0.95),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "output_tokens_per_second": round(output_tokens / elapsed, 4),
        "errors": len(results) - len(successful),
        "timeouts": timeouts,
        "gpu_utilization_mean_percent": (
            round(statistics.mean(s["utilization_percent"] for s in gpu_samples), 2)
            if gpu_samples
            else None
        ),
        "gpu_utilization_max_percent": (
            max(s["utilization_percent"] for s in gpu_samples) if gpu_samples else None
        ),
        "gpu_memory_max_mib": (
            max(s["memory_used_mib"] for s in gpu_samples) if gpu_samples else None
        ),
    }


def main() -> int:
    model = _model()
    results = []
    for concurrency in CONCURRENCY_LEVELS:
        result = _run_level(model, concurrency)
        results.append(result)
        if result["errors"] or result["timeouts"]:
            break
    print(
        json.dumps(
            {
                "model": model,
                "fixed_prompt": PROMPT,
                "max_tokens": MAX_TOKENS,
                "results": results,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
