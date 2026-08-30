"""The canonical embedding boundary memory vectors come from.

The contract these tests hold is negative as much as positive: when the
embedding service cannot answer, the client raises. It never substitutes a
locally derived vector, because a memory indexed against a non-semantic vector
would silently poison retrieval instead of visibly failing.
"""

import pytest

from app.core.config import settings
from app.services import memory_embedding_client as embedding_module
from app.services.memory_embedding_client import MemoryEmbeddingClient, MemoryEmbeddingError

from unittest.mock import Mock


def _client(monkeypatch, vector):
    client = MemoryEmbeddingClient(Mock())
    sent = {}

    async def fake_request(text):
        sent["text"] = text
        if isinstance(vector, Exception):
            raise vector
        return vector

    monkeypatch.setattr(client, "_request_embedding", fake_request)
    return client, sent


def test_stored_memory_is_embedded_as_a_passage_and_a_query_as_a_query(monkeypatch):
    dimensions = settings.memory_embedding_dimensions
    client, sent = _client(monkeypatch, [0.1] * dimensions)

    client.embed_memory("the user prefers concise answers")
    passage_text = sent["text"]
    client.embed_query("how does the user like answers")
    query_text = sent["text"]

    assert passage_text.startswith(settings.memory_embedding_passage_prefix)
    assert query_text.startswith(settings.memory_embedding_query_prefix)


def test_one_request_is_bounded_to_the_configured_character_budget(monkeypatch):
    dimensions = settings.memory_embedding_dimensions
    client, sent = _client(monkeypatch, [0.1] * dimensions)

    client.embed_memory("x" * (settings.memory_embedding_max_chars * 3))

    prefix = settings.memory_embedding_passage_prefix
    assert len(sent["text"]) == len(prefix) + settings.memory_embedding_max_chars


def test_empty_text_is_refused_before_a_request_is_made(monkeypatch):
    client, sent = _client(monkeypatch, [0.1])

    with pytest.raises(MemoryEmbeddingError):
        client.embed_memory("   ")

    assert sent == {}


def test_a_vector_of_the_wrong_dimensionality_is_an_error(monkeypatch):
    client, _ = _client(monkeypatch, [0.1] * (settings.memory_embedding_dimensions - 1))

    with pytest.raises(MemoryEmbeddingError) as raised:
        client.embed_query("anything")

    assert "dimensionality mismatch" in str(raised.value)


def test_an_empty_reply_is_an_error_rather_than_a_substitute_vector(monkeypatch):
    client, _ = _client(monkeypatch, [])

    with pytest.raises(MemoryEmbeddingError):
        client.embed_query("anything")


def test_a_transport_failure_surfaces_as_a_memory_embedding_error(monkeypatch):
    client, _ = _client(monkeypatch, RuntimeError("connection refused"))

    with pytest.raises(MemoryEmbeddingError) as raised:
        client.embed_query("anything")

    assert "connection refused" in str(raised.value)


def test_reply_parsing_reports_the_services_own_error(monkeypatch):
    monkeypatch.setattr(embedding_module, "verify_internal_ticket_from_envelope", lambda *a, **k: None)
    client = MemoryEmbeddingClient(Mock())

    with pytest.raises(MemoryEmbeddingError) as raised:
        client._vector_from_reply({"data": {"embedding": [], "error": "Embedding model not available"}})

    assert "Embedding model not available" in str(raised.value)


def test_reply_parsing_returns_the_vector_the_service_sent(monkeypatch):
    monkeypatch.setattr(embedding_module, "verify_internal_ticket_from_envelope", lambda *a, **k: None)
    client = MemoryEmbeddingClient(Mock())

    assert client._vector_from_reply({"data": {"embedding": [0.1, 0.2]}}) == [0.1, 0.2]


def test_provenance_names_the_model_and_dimensionality_of_memory_vectors():
    client = MemoryEmbeddingClient(Mock())

    provenance = client.provenance()

    assert provenance["model"] == settings.memory_embedding_model
    assert provenance["dimensions"] == settings.memory_embedding_dimensions
    assert provenance["service"] == settings.embedding_queue
