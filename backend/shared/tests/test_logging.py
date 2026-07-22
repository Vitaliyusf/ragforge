"""Security-focused tests for structured log redaction."""
from shared.logging import REDACTED, redact_value


def test_sensitive_credentials_and_private_content_are_redacted_recursively() -> None:
    redacted = redact_value({
        "headers": {
            "Authorization": "Bearer secret",
            "X-Internal-Auth": "signed-ticket",
            "Cookie": "session=secret",
        },
        "payload": {
            "question": "private question",
            "content_b64": "private-file-content",
            "metadata": {"safe": "retained"},
        },
    })

    assert redacted["headers"] == {
        "Authorization": REDACTED,
        "X-Internal-Auth": REDACTED,
        "Cookie": REDACTED,
    }
    assert redacted["payload"]["question"] == REDACTED
    assert redacted["payload"]["content_b64"] == REDACTED
    assert redacted["payload"]["metadata"] == {"safe": "retained"}
