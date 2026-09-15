import pytest
from pydantic import ValidationError

from agent.context import ProcurementContext


def test_context_contains_only_trusted_minimum_identity_scope() -> None:
    context = ProcurementContext(
        user_id="user-1",
        username="buyer",
        thread_id="thread-1",
        trace_id="trace-1",
        roles=frozenset({"buyer"}),
        language="zh-CN",
        timezone="Asia/Shanghai",
    )

    assert set(context.model_dump()) == {
        "user_id",
        "username",
        "thread_id",
        "trace_id",
        "roles",
        "language",
        "timezone",
    }


def test_context_rejects_secret_or_raw_token_fields() -> None:
    with pytest.raises(ValidationError):
        ProcurementContext(
            user_id="user-1",
            roles=frozenset({"buyer"}),
            trace_id="trace-1",
            api_key="secret",
        )
