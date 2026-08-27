"""Best-effort Prometheus snapshots attached to benchmark artifacts.

Benchmarks measure tenant-scoped golden sets, while Prometheus measures the
platform. This collector deliberately stores the latter as evidence only and
never puts tenant or benchmark identifiers into metric labels.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

import aiohttp

PROMETHEUS_SCOPE = "all_tenants"
_TIMEOUT_SECONDS = 5.0

# Existing live-traffic series from the gateway metrics integration. Quality
# has no Prometheus series; its empty section explicitly records that fact.
SNAPSHOT_QUERIES: Dict[str, Dict[str, str]] = {
    "overview": {
        "qps": "sum(rate(ragapp_rag_queries_total[5m]))",
        "error_rate": 'sum(rate(ragapp_rag_queries_total{status="error"}[5m])) / clamp_min(sum(rate(ragapp_rag_queries_total[5m])), 0.000000001)',
    },
    "latency": {
        "turn_latency_p95": "histogram_quantile(0.95, sum by (answer_mode, le) (rate(ragapp_rag_query_duration_seconds_bucket[5m])))",
        "ttft_p95": "histogram_quantile(0.95, sum by (answer_mode, le) (rate(ragapp_rag_ttft_seconds_bucket[5m])))",
        "stage_p95": "histogram_quantile(0.95, sum by (stage, le) (rate(ragapp_rag_stage_duration_seconds_bucket[5m])))",
    },
    "retrieval": {
        "vector_search_p95": 'histogram_quantile(0.95, sum by (collection, le) (rate(ragapp_vector_search_duration_seconds_bucket{traffic_class="live"}[5m])))',
        "vector_search_rate": 'sum by (collection) (rate(ragapp_vector_searches_total{traffic_class="live"}[5m]))',
        "reranker_p95": 'histogram_quantile(0.95, sum by (le) (rate(ragapp_reranker_duration_seconds_bucket{traffic_class="live"}[5m])))',
    },
    "quality": {},
    "pipeline": {
        "embedding_p95": 'histogram_quantile(0.95, sum by (le) (rate(ragapp_embedding_duration_seconds_bucket{traffic_class="live"}[5m])))',
        "llm_p95": 'histogram_quantile(0.95, sum by (model, le) (rate(ragapp_llm_request_duration_seconds_bucket{traffic_class="live"}[5m])))',
        "llm_p50_by_request_type": "histogram_quantile(0.50, sum by (request_type, traffic_class, le) (rate(ragapp_llm_request_duration_seconds_bucket[5m])))",
        "llm_p95_by_request_type": "histogram_quantile(0.95, sum by (request_type, traffic_class, le) (rate(ragapp_llm_request_duration_seconds_bucket[5m])))",
        "llm_provider_p95_by_request_type": "histogram_quantile(0.95, sum by (request_type, traffic_class, le) (rate(ragapp_llm_provider_duration_seconds_bucket[5m])))",
        "llm_wall_time_rate": "sum by (request_type, traffic_class) (rate(ragapp_llm_request_duration_seconds_sum[5m]))",
        "llm_request_rate": "sum by (request_type, traffic_class) (rate(ragapp_llm_requests_total[5m]))",
        "llm_error_rate": "sum by (request_type, traffic_class) (rate(ragapp_llm_errors_total[5m]))",
        "llm_input_token_rate": 'sum by (request_type, traffic_class) (rate(ragapp_llm_tokens_total{direction="input"}[5m]))',
        "llm_output_token_rate": 'sum by (request_type, traffic_class) (rate(ragapp_llm_tokens_total{direction="output"}[5m]))',
        "llm_total_token_rate": 'sum by (request_type, traffic_class) (rate(ragapp_llm_tokens_total{direction="total"}[5m]))',
        # Legacy series: an application parse failure is counted here as
        # `error`, hiding the provider's own reason. Kept for continuity with
        # earlier runs; read the provider series below for what the model did.
        "llm_finish_reason_rate": "sum by (request_type, traffic_class, finish_reason) (rate(ragapp_llm_finish_reasons_total[5m]))",
        "llm_provider_finish_reason_rate": "sum by (request_type, traffic_class, finish_reason) (rate(ragapp_llm_provider_finish_reasons_total[5m]))",
        "llm_output_tokens_p50_by_request_type": "histogram_quantile(0.50, sum by (request_type, traffic_class, le) (rate(ragapp_llm_output_tokens_bucket[5m])))",
        "llm_output_tokens_p95_by_request_type": "histogram_quantile(0.95, sum by (request_type, traffic_class, le) (rate(ragapp_llm_output_tokens_bucket[5m])))",
        "llm_output_tokens_p99_by_request_type": "histogram_quantile(0.99, sum by (request_type, traffic_class, le) (rate(ragapp_llm_output_tokens_bucket[5m])))",
        "ingestion_stage_rate": "sum by (stage, outcome) (rate(ragapp_ingestion_stage_total[5m]))",
    },
    # The vLLM server's own view of itself, scraped from vllm:8000/metrics.
    # RAGForge's ragapp_llm_* series measure the client side of the same
    # requests; these measure the scheduler behind them — what was running,
    # what was queued, how full the KV cache was, what the prefix cache hit.
    #
    # Metric names are not identical across vLLM releases and this repository
    # cannot prove which ones a given image exposes without running it, so
    # where a name moved between engine versions both spellings are queried.
    # A name the running server does not export returns an empty result, which
    # is recorded as "no data" — never as a zero. Reading an empty list here
    # as "no preemptions occurred" would be exactly the wrong conclusion.
    "vllm": {
        # Whether the scrape target is even up. Without this, every other
        # empty result below is ambiguous between "vLLM did not export it"
        # and "Prometheus never reached vLLM".
        "scrape_up": 'up{job="vllm"}',
        "num_requests_running": "vllm:num_requests_running",
        "num_requests_waiting": "vllm:num_requests_waiting",
        # v1 renamed the KV-cache gauge; older releases used the gpu_ spelling.
        "kv_cache_usage_perc": "vllm:kv_cache_usage_perc",
        "gpu_cache_usage_perc": "vllm:gpu_cache_usage_perc",
        "prefix_cache_queries_total": "vllm:prefix_cache_queries_total",
        "prefix_cache_hits_total": "vllm:prefix_cache_hits_total",
        "prompt_tokens_total": "vllm:prompt_tokens_total",
        "generation_tokens_total": "vllm:generation_tokens_total",
        "prompt_token_rate": "sum by (model_name) (rate(vllm:prompt_tokens_total[5m]))",
        "generation_token_rate": "sum by (model_name) (rate(vllm:generation_tokens_total[5m]))",
        "finish_reason_total": "sum by (model_name, finished_reason) (vllm:request_success_total)",
        "ttft_p50": "histogram_quantile(0.50, sum by (model_name, le) (rate(vllm:time_to_first_token_seconds_bucket[5m])))",
        "ttft_p95": "histogram_quantile(0.95, sum by (model_name, le) (rate(vllm:time_to_first_token_seconds_bucket[5m])))",
        "inter_token_latency_p50": "histogram_quantile(0.50, sum by (model_name, le) (rate(vllm:time_per_output_token_seconds_bucket[5m])))",
        "inter_token_latency_p95": "histogram_quantile(0.95, sum by (model_name, le) (rate(vllm:time_per_output_token_seconds_bucket[5m])))",
        # Preemption/recompute counters, whose name also moved between engine
        # versions. Both empty means the release exposes neither, not zero.
        "num_preemptions_total": "vllm:num_preemptions_total",
        "request_preemptions_total": "vllm:request_preemptions_total",
        # Info-style series: whatever the running server chose to publish
        # about its resolved cache configuration, recorded verbatim rather
        # than re-derived from flags RAGForge believes it passed.
        "cache_config_info": "vllm:cache_config_info",
    },
}


def _empty_snapshot() -> Dict[str, Any]:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "prometheus_available": False,
        "prometheus_scope": PROMETHEUS_SCOPE,
        "sections": {name: {} for name in SNAPSHOT_QUERIES},
    }


class BenchmarkPrometheusSnapshotter:
    """Capture a bounded set of platform metrics without raising outward."""

    def __init__(self, base_url: str, *, timeout: float = _TIMEOUT_SECONDS) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def capture(self) -> Dict[str, Any]:
        snapshot = _empty_snapshot()
        names = [
            (section, name, query)
            for section, values in SNAPSHOT_QUERIES.items()
            for name, query in values.items()
        ]
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(base_url=self.base_url, timeout=timeout) as client:
                async with client.get("/-/healthy") as healthy:
                    if healthy.status != 200:
                        return snapshot
                results = await asyncio.gather(
                    *(self._query(client, query) for _, _, query in names),
                    return_exceptions=True,
                )
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return snapshot

        available = True
        for (section, name, _), result in zip(names, results):
            if isinstance(result, Exception):
                available = False
            else:
                snapshot["sections"][section][name] = result
        snapshot["prometheus_available"] = available
        return snapshot

    @staticmethod
    async def _query(client: aiohttp.ClientSession, query: str) -> List[Dict[str, Any]]:
        async with client.get("/api/v1/query", params={"query": query}) as response:
            if response.status != 200:
                raise RuntimeError(f"Prometheus returned HTTP {response.status}")
            body = await response.json()
        if not isinstance(body, dict) or body.get("status") != "success":
            raise RuntimeError("Prometheus returned an invalid query response")
        result = (body.get("data") or {}).get("result")
        return result if isinstance(result, list) else []


class NullBenchmarkPrometheusSnapshotter:
    """No-op collaborator for direct unit construction of the runner."""

    async def capture(self) -> Dict[str, Any]:
        return _empty_snapshot()
