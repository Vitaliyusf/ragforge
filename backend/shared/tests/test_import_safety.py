"""Import and serialization contracts for the shared package."""
from pathlib import Path
import subprocess
import sys

from shared.errors import DatabaseException, public_error_payload


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_importing_shared_does_not_eagerly_import_infrastructure_modules() -> None:
    script = """
import sys
import shared

unexpected = {
    "shared.metrics",
    "shared.circuit_breaker",
    "shared.rate_limiter",
    "shared.dlq",
}.intersection(sys.modules)
assert not unexpected, unexpected
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_public_error_payload_omits_private_cause_by_default() -> None:
    error = DatabaseException(
        "Database operation failed",
        details={"operation": "read"},
        original_exception=RuntimeError("db-password=secret"),
    )

    payload = public_error_payload(error)

    assert payload["code"] == "DATABASE_ERROR"
    assert payload["message"] == "Database operation failed"
    assert payload["retryable"] is False
    assert "cause" not in payload
    assert "stack" not in payload
    assert "secret" not in str(payload)
