import logging

import pytest
from pydantic import ValidationError

from mcp_server.error_mapper import error_envelope
from mcp_server.schemas import ToolEnvelope, ToolError
from procurepilot.business.errors import (
    ApprovalRequiredError,
    ConflictError,
    DomainValidationError,
    EntityNotFoundError,
    PermissionDeniedError,
)


def test_success_envelope_requires_data_without_error() -> None:
    envelope = ToolEnvelope[list[int]](ok=True, data=[1, 2], error=None, trace_id="trace-1")

    assert envelope.model_dump(mode="json") == {
        "ok": True,
        "data": [1, 2],
        "error": None,
        "trace_id": "trace-1",
    }
    with pytest.raises(ValidationError):
        ToolEnvelope[int](
            ok=True,
            data=1,
            error=ToolError(code="CONFLICT", message="conflict", retryable=False),
            trace_id="trace-1",
        )


@pytest.mark.parametrize(
    ("error", "expected_code", "retryable"),
    [
        (DomainValidationError("bad input"), "VALIDATION_ERROR", False),
        (EntityNotFoundError("missing"), "NOT_FOUND", False),
        (ConflictError("conflict"), "CONFLICT", False),
        (PermissionDeniedError("denied"), "PERMISSION_DENIED", False),
        (ApprovalRequiredError("approval"), "APPROVAL_REQUIRED", False),
        (TimeoutError(), "DEPENDENCY_TIMEOUT", True),
    ],
)
def test_known_errors_map_to_stable_codes(
    error: Exception,
    expected_code: str,
    retryable: bool,
) -> None:
    envelope = error_envelope(error, trace_id="trace-2")

    assert envelope.ok is False
    assert envelope.data is None
    assert envelope.error is not None
    assert envelope.error.code == expected_code
    assert envelope.error.retryable is retryable


def test_internal_error_hides_exception_details_and_logs_only_trace_id(caplog) -> None:
    caplog.set_level(logging.ERROR)
    error = RuntimeError("password=secret; D:\\private\\file; mysql://admin:secret@host/db")

    envelope = error_envelope(error, trace_id="trace-safe-3")

    assert envelope.error is not None
    assert envelope.error.code == "INTERNAL_ERROR"
    assert envelope.error.message == "Internal error"
    combined = envelope.model_dump_json() + caplog.text
    assert "secret" not in combined
    assert "private" not in combined
    assert "trace-safe-3" in caplog.text
