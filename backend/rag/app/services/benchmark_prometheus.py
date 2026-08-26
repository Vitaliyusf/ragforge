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
        "ingestion_stage_rate": "sum by (stage, outcome) (rate(ragapp_ingestion_stage_total[5m]))",
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
