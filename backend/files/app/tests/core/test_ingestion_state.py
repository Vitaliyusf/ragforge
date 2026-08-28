"""State-transition contract for deterministic file ingestion."""
from __future__ import annotations

import pytest

from app.core.constants import IngestionState
from app.services.ingestion_state import transition_ingestion_state


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (IngestionState.LOAD_EXTRACTION_RESULT, IngestionState.DETECT_ISSUES),
        (IngestionState.DETECT_ISSUES, IngestionState.AWAIT_HUMAN_REVIEW),
        (IngestionState.DETECT_ISSUES, IngestionState.CHUNK_TEXT),
        (IngestionState.AWAIT_HUMAN_REVIEW, IngestionState.APPLY_DECISION),
        (IngestionState.APPLY_DECISION, IngestionState.CHUNK_TEXT),
        (IngestionState.APPLY_DECISION, IngestionState.FINALIZE),
        (IngestionState.CHUNK_TEXT, IngestionState.REQUEST_EMBEDDINGS),
        (IngestionState.REQUEST_EMBEDDINGS, IngestionState.FINALIZE),
    ],
)
def test_allowed_ingestion_transitions_are_explicit(current, target):
    assert transition_ingestion_state(current.value, target) == target.value


def test_ingestion_rejects_transition_that_skips_domain_work():
    with pytest.raises(ValueError, match="Invalid ingestion transition"):
        transition_ingestion_state(
            IngestionState.DETECT_ISSUES.value,
            IngestionState.FINALIZE,
        )
