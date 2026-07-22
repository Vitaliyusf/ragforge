"""Proxy spoofing tests for the HTTP rate-limit identity."""
from typing import Any

import pytest
from starlette.requests import Request

from shared.rate_limiter import RateLimiterMiddleware


async def _app(scope: Any, receive: Any, send: Any) -> None:
    return None


def _request(peer: str, forwarded: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/test",
            "headers": [(b"x-forwarded-for", forwarded.encode("ascii"))],
            "client": (peer, 12345),
            "server": ("test", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_untrusted_peer_cannot_spoof_forwarded_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    middleware = RateLimiterMiddleware(_app)
    assert middleware._client_ip(_request("203.0.113.10", "198.51.100.7")) == "203.0.113.10"


def test_trusted_proxy_may_supply_one_valid_client_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    middleware = RateLimiterMiddleware(_app)
    assert middleware._client_ip(_request("127.0.0.1", "198.51.100.7, 127.0.0.1")) == "198.51.100.7"


def test_malformed_forwarded_address_falls_back_to_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    middleware = RateLimiterMiddleware(_app)
    assert middleware._client_ip(_request("127.0.0.1", "not-an-ip")) == "127.0.0.1"
