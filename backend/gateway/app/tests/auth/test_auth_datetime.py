"""Regression tests for Mongo's legacy timezone-naive session timestamps."""
from datetime import datetime, timezone

from app.services.auth_service import _as_utc


def test_as_utc_marks_legacy_naive_datetime_as_utc() -> None:
    legacy = datetime(2026, 7, 16, 12, 30, 0)

    normalized = _as_utc(legacy)

    assert normalized.tzinfo == timezone.utc
    assert normalized.hour == 12


def test_as_utc_preserves_aware_instant() -> None:
    aware = datetime(2026, 7, 16, 12, 30, 0, tzinfo=timezone.utc)

    assert _as_utc(aware) == aware
