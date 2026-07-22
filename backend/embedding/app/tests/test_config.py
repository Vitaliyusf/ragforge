"""Focused configuration tests for the embedding service."""

from app.config import EmbeddingConfig


def test_defaults_align_with_active_upload_runtime(monkeypatch):
    """Default topics should match the current files-to-embedding runtime."""

    monkeypatch.delenv("EXTRACT_TOPIC", raising=False)
    monkeypatch.delenv("FILES_TOPIC", raising=False)

    config = EmbeddingConfig()

    assert config.extract_topic == "embedding.requests"
    assert config.files_topic == "files.requests"


def test_topic_env_overrides_still_take_precedence(monkeypatch):
    """Environment variables should still override the runtime defaults."""

    monkeypatch.setenv("EXTRACT_TOPIC", "custom.extract.topic")
    monkeypatch.setenv("FILES_TOPIC", "custom.files.topic")

    config = EmbeddingConfig()

    assert config.extract_topic == "custom.extract.topic"
    assert config.files_topic == "custom.files.topic"
