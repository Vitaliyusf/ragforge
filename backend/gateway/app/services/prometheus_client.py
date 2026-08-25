"""Thin async HTTP client for the Prometheus query API.

Not a :class:`BaseRPCService`: Prometheus speaks HTTP, not RabbitMQ.

Availability is a first-class concept here. Every failure path raises
:class:`PrometheusUnavailable` rather than leaking an ``httpx`` exception, so
callers can turn a dead metrics container into ``{"prometheus_available":
false}`` and degraded panels instead of a 5xx. A monitoring outage must not
take the tab down with it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import httpx

# Percentile queries are cheap. A slow Prometheus must never hold a gateway
# worker long enough to matter, so the timeout is deliberately short.
DEFAULT_TIMEOUT_SECONDS = 5.0


class PrometheusUnavailable(RuntimeError):
    """Prometheus could not be reached, or returned an unusable response."""


class PrometheusClient:
    """Query Prometheus over HTTP through one shared connection pool."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        """Close the shared connection pool."""
        await self._client.aclose()

    async def is_available(self) -> bool:
        """Report whether Prometheus is reachable and healthy.

        Never raises: the answer to "is the metrics backend up" is a bool,
        and any caller asking it is already handling the negative case.
        """
        try:
            response = await self._client.get("/-/healthy")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def query(self, expr: str) -> List[Dict[str, Any]]:
        """Run an instant query and return its ``result`` list.

        Args:
            expr: A PromQL expression, rendered by ``promql.render()``.

        Returns:
            The raw ``data.result`` entries. Empty when the query matched
            nothing, which is a real answer rather than a failure.

        Raises:
            PrometheusUnavailable: On any transport error, a non-200 status,
                or a body that is not a successful Prometheus envelope.
        """
        return await self._get("/api/v1/query", {"query": expr})

    async def query_range(
        self,
        expr: str,
        start: Union[str, float],
        end: Union[str, float],
        step: str,
    ) -> List[Dict[str, Any]]:
        """Run a range query and return its ``result`` list.

        Args:
            expr: A PromQL expression, rendered by ``promql.render()``.
            start: Range start, as a UNIX timestamp or an RFC 3339 string.
            end: Range end, in the same form as ``start``.
            step: Resolution step, for example ``"15m"``.

        Returns:
            The raw ``data.result`` entries, each carrying a ``values`` list
            of ``[timestamp, value]`` pairs.

        Raises:
            PrometheusUnavailable: As for :meth:`query`.
        """
        return await self._get(
            "/api/v1/query_range",
            {"query": expr, "start": str(start), "end": str(end), "step": step},
        )

    async def _get(self, path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        """Issue one API request and unwrap the Prometheus response envelope."""
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise PrometheusUnavailable(f"Prometheus request failed: {exc}") from exc

        if response.status_code != 200:
            raise PrometheusUnavailable(
                f"Prometheus returned HTTP {response.status_code}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise PrometheusUnavailable("Prometheus returned a non-JSON body") from exc

        if not isinstance(body, dict) or body.get("status") != "success":
            raise PrometheusUnavailable("Prometheus reported a failed query")

        result = (body.get("data") or {}).get("result")
        return result if isinstance(result, list) else []
