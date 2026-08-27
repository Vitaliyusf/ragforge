"""Fail-closed startup tests for the Gateway security boundary."""
from __future__ import annotations

import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.core.config import GatewayConfig
from app.main import app
from shared.rate_limiter import RateLimiterMiddleware
from shared.security import SecurityHeadersMiddleware


def test_required_security_middleware_is_installed() -> None:
    middleware_classes = {entry.cls for entry in app.user_middleware}

    assert SecurityHeadersMiddleware in middleware_classes
    assert RateLimiterMiddleware in middleware_classes


def test_missing_required_security_component_aborts_import() -> None:
    import_script = """
import builtins

original_import = builtins.__import__

def fail_security_import(name, *args, **kwargs):
    if name == "shared.security":
        raise ImportError("simulated missing required security component")
    return original_import(name, *args, **kwargs)

builtins.__import__ = fail_security_import
import app.main
"""

    completed = subprocess.run(
        [sys.executable, "-c", import_script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "simulated missing required security component" in completed.stderr


@pytest.mark.parametrize(
    ("auth_required", "session_cookie_secure", "message"),
    [
        (False, True, "AUTH_REQUIRED must be true in production"),
        (True, False, "SESSION_COOKIE_SECURE must be true in production"),
    ],
)
def test_production_security_misconfiguration_fails_closed(
    auth_required: bool,
    session_cookie_secure: bool,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        GatewayConfig(
            environment="production",
            auth_required=auth_required,
            session_cookie_secure=session_cookie_secure,
            session_cookie_name="__Host-ragapp_session",
            csrf_cookie_name="__Host-ragapp_csrf",
            internal_auth_secret="internal-auth-secret-with-32-bytes-minimum",
            password_pepper="password-pepper-with-at-least-32-bytes",
            session_pepper="session-pepper-with-at-least-32-bytes",
            cors_origins="https://app.example.test",
        )
