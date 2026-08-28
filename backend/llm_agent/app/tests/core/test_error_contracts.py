"""Shared and LLM-owned error ownership contracts."""
from app.core.errors import (
    BaseServiceException,
    NotFoundException,
    StreamingNotSupportedException,
    TimeoutException,
    ValidationException,
)
from shared.errors import AppError, ErrorCode, NotFoundError, TimeoutException as SharedTimeout
from shared.errors import ValidationError


def test_common_llm_errors_use_the_canonical_shared_contract() -> None:
    assert BaseServiceException is AppError
    assert NotFoundException is NotFoundError
    assert TimeoutException is SharedTimeout
    assert ValidationException is ValidationError


def test_streaming_error_remains_llm_owned_and_transport_safe() -> None:
    error = StreamingNotSupportedException(
        "provider cannot stream",
        details={"provider": "local"},
    )

    assert isinstance(error, AppError)
    assert error.error_code is ErrorCode.LLM_STREAMING_NOT_SUPPORTED
    assert error.status_code == 400
    assert error.to_dict()["details"] == {"provider": "local"}
