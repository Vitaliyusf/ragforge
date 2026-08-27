"""Regression tests for embedding model load resilience.

A transient huggingface fetch failure used to leave the service running with
``embedding_model = None`` forever, so every request returned
"Embedding model not available" until someone restarted the container.
"""

import pytest

from app.config import EmbeddingConfig
from app.embedding import factories
from app.embedding.factories import EmbeddingModelFactory


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL_TYPE", "sentence_transformers")
    monkeypatch.setenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
    return EmbeddingConfig()


def test_transient_load_failure_is_retried_before_giving_up(config, monkeypatch):
    """A model that loads on the second attempt should still be returned."""

    attempts = []

    class FlakyModel:
        def __init__(self, model_name):
            attempts.append(model_name)
            if len(attempts) == 1:
                raise RuntimeError("Failed to load: connection reset by peer")

        def is_loaded(self):
            return True

    monkeypatch.setattr(factories, "SentenceTransformerModel", FlakyModel)
    monkeypatch.setattr(factories.time, "sleep", lambda _seconds: None)

    model = EmbeddingModelFactory.create(config)

    assert model is not None
    assert len(attempts) == 2


def test_persistent_load_failure_still_returns_none_after_bounded_retries(
    config, monkeypatch
):
    """Retries must be bounded so startup cannot hang indefinitely."""

    attempts = []

    class AlwaysFailingModel:
        def __init__(self, model_name):
            attempts.append(model_name)
            raise RuntimeError("Failed to load: gateway timeout")

    monkeypatch.setattr(factories, "SentenceTransformerModel", AlwaysFailingModel)
    monkeypatch.setattr(factories, "LangChainEmbeddingModel", AlwaysFailingModel)
    monkeypatch.setattr(factories.time, "sleep", lambda _seconds: None)

    model = EmbeddingModelFactory.create(config)

    assert model is None
    assert 1 < len(attempts) <= factories.MODEL_LOAD_MAX_ATTEMPTS
