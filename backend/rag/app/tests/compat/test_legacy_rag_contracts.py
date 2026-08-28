"""Compatibility lane: legacy answer-mode and pre-versioning llm_agent reply shapes.

Retire these together with the production compatibility paths they cover."""
from __future__ import annotations

import pytest

from app.services.conversation_messages import (
    build_message_envelope,
    extract_reply_payload,
)
from app.tests._service_harness import (
    TEST_IDENTITY,
    build_service,
)


pytestmark = pytest.mark.compat
def test_normalize_legacy_answer_mode_quick_to_regular():
    service, _, _ = build_service()
    request = service.build_request({"question": "hello", "answer_mode": "quick"})
    assert request.mode == "regular"
    assert request.owner_type == "user"
    assert request.owner_id == TEST_IDENTITY.user_id
    assert request.tenant_id == TEST_IDENTITY.tenant_id


def test_extract_reply_payload_supports_shared_and_legacy_shapes():
    shared = build_message_envelope(
        message_type="reply",
        action="search_chunks",
        source_service="vector_db",
        target_service="rag",
        request_id="request-1",
        trace_id="trace-1",
        correlation_id="corr-1",
        payload={"chunks": [{"chunk_id": "c1"}]},
    )
    shared["success"] = True

    legacy = {"correlation_id": "corr-legacy", "data": {"chunks": [{"chunk_id": "legacy"}]}}

    assert extract_reply_payload(shared)["chunks"][0]["chunk_id"] == "c1"
    assert extract_reply_payload(legacy)["chunks"][0]["chunk_id"] == "legacy"


