import pytest
from pydantic import ValidationError

from mcp_server.context import MissingCallerContextProvider, ToolCallerContext
from procurepilot.business.errors import PermissionDeniedError


def test_valid_caller_context_is_immutable() -> None:
    context = ToolCallerContext(
        user_id="buyer-1", roles=frozenset({"procurement_reader"}), trace_id="trace:1"
    )

    assert context.user_id == "buyer-1"
    with pytest.raises(ValidationError):
        context.user_id = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    "values",
    [
        {"roles": frozenset({"procurement_reader"}), "trace_id": "trace-1"},
        {"user_id": "user-1", "roles": frozenset(), "trace_id": "trace-1"},
        {"user_id": "user-1", "roles": frozenset({"unknown"}), "trace_id": "trace-1"},
        {
            "user_id": "user-1",
            "roles": frozenset({"procurement_reader"}),
            "trace_id": "bad trace",
        },
    ],
)
def test_invalid_or_missing_identity_fails_closed(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ToolCallerContext.model_validate(values)


@pytest.mark.asyncio
async def test_missing_trusted_provider_fails_closed() -> None:
    with pytest.raises(PermissionDeniedError):
        await MissingCallerContextProvider().get_context()
