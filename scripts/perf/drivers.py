"""HTTP drivers that turn a :class:`ScenarioSpec` into a measurable call.

Kept apart from the harness so the outcome classification — the part that
decides whether a response counts as a success, a fallback, a timeout or an
error — is pure and directly testable without a socket. Under load that
classification is the number everyone argues about, so it should not be
reachable only through a live stack.

The gateway authenticates with a session cookie plus a CSRF header on unsafe
methods, so :class:`GatewaySession` logs in once and reuses the cookie jar for
the whole run. Logging in per request would put an auth round trip inside
every measured latency and would measure the login path instead.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .harness import CallResult
from .runtime import monotonic
from .scenarios import HttpCall, ScenarioSpec

# Status codes that mean the request ran out of time rather than failed. Both
# are recorded as timeouts so they land with the client-side expiries instead
# of being averaged into a generic error count.
TIMEOUT_STATUS_CODES = frozenset({408, 504})

# Gateway cookie names, matching GatewayConfig's defaults. Overridable because
# a hardened deployment prefixes them with `__Host-`.
DEFAULT_SESSION_COOKIE = "ragapp_session"
DEFAULT_CSRF_COOKIE = "ragapp_csrf"

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def classify_response(
    status_code: int,
    payload: Any,
    classify: Optional[Callable[[Any], str]] = None,
) -> str:
    """Decide how one HTTP response counts toward the profile.

    A 2xx is handed to the scenario's own classifier, which is the only thing
    that can tell a healthy answer from a degraded one; without a classifier a
    2xx is a plain success rather than an assumed fallback.

    Args:
        status_code: HTTP status the service returned.
        payload: Decoded JSON body, or ``None`` when it could not be decoded.
        classify: The scenario's fallback detector.
    """
    if 200 <= status_code < 300:
        if classify is None:
            return "success"
        outcome = classify(payload)
        if outcome not in ("success", "fallback"):
            raise ValueError(
                f"scenario classifier returned {outcome!r}; a 2xx response is "
                "either a success or a fallback"
            )
        return outcome
    if status_code in TIMEOUT_STATUS_CODES:
        return "timeout"
    return "error"


def _decode(response: Any) -> Any:
    """Best-effort JSON body. A body we cannot read never fails the call."""
    try:
        return response.json()
    except Exception:
        return None


class GatewaySession:
    """An authenticated httpx client for the gateway.

    Wraps the client rather than subclassing it so the CSRF rule lives in one
    place: the gateway requires the header on every unsafe method, and a
    driver that forgets it measures a wall of 401s and calls them errors.
    """

    def __init__(
        self,
        client: Any,
        session_cookie: str = DEFAULT_SESSION_COOKIE,
        csrf_cookie: str = DEFAULT_CSRF_COOKIE,
    ) -> None:
        self._client = client
        self._session_cookie = session_cookie
        self._csrf_cookie = csrf_cookie

    @property
    def authenticated(self) -> bool:
        return bool(self._client.cookies.get(self._session_cookie))

    async def login(self, username: str, password: str) -> None:
        """Establish the session used for every measured call."""
        response = await self._client.post(
            "/v1/auth/login", json={"username": username, "password": password}
        )
        response.raise_for_status()

    def headers(self, method: str) -> Dict[str, str]:
        """Headers for one request, including CSRF on unsafe methods."""
        if method.upper() in SAFE_METHODS:
            return {}
        token = self._client.cookies.get(self._csrf_cookie)
        return {"x-csrf-token": token} if token else {}

    async def request(self, call: HttpCall, index: int) -> Any:
        method = call.method.upper()
        return await self._client.request(
            method,
            call.path,
            json=call.body(index) if call.body else None,
            params=call.params(index) if call.params else None,
            headers=self.headers(method),
        )


def http_call_fn(session: GatewaySession, spec: ScenarioSpec) -> Callable[[int], Any]:
    """Build the measured call for an HTTP scenario.

    Client-side transport failures are deliberately not caught here: the
    harness classifies them, so every scenario reports a connection reset the
    same way rather than each driver inventing its own rule.
    """
    if spec.http is None:
        raise ValueError(f"scenario {spec.name!r} has no HTTP call to drive")

    async def call(index: int) -> CallResult:
        started = monotonic()
        response = await session.request(spec.http, index)
        latency = monotonic() - started
        outcome = classify_response(response.status_code, _decode(response), spec.classify)
        return CallResult(outcome=outcome, latency_seconds=latency)

    return call
