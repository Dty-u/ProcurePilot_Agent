import pytest
from langgraph.store.memory import InMemoryStore
from pydantic import ValidationError

from agent.context import ProcurementContext
from agent.memory.preferences import PreferenceUpdate, UserPreferenceRepository


def context(user_id: str) -> ProcurementContext:
    return ProcurementContext(
        user_id=user_id,
        roles=frozenset({"procurement_reader"}),
        thread_id=f"thread-{user_id}",
        trace_id=f"trace-{user_id}",
    )


@pytest.mark.asyncio
async def test_preferences_round_trip_and_are_isolated_by_user() -> None:
    store = InMemoryStore()
    repository = UserPreferenceRepository(store)
    saved = await repository.update(
        context("user-1"),
        PreferenceUpdate(
            preferred_output="table",
            preferred_currency="CNY",
            recent_suppliers=("supplier-1",),
            recent_queries=("物料 A 报价",),
        ),
    )
    assert saved.preferred_currency == "CNY"

    first_user = await repository.get(context("user-1"))
    other_user = await repository.get(context("user-2"))

    assert first_user.preferred_output == "table"
    assert first_user.recent_suppliers == ("supplier-1",)
    assert other_user.preferred_output is None
    assert other_user.recent_suppliers == ()


def test_preference_update_rejects_unknown_or_sensitive_fields() -> None:
    with pytest.raises(ValidationError):
        PreferenceUpdate.model_validate({"roles": ["admin"]})
    with pytest.raises(ValidationError):
        PreferenceUpdate.model_validate({"api_key": "secret"})
    with pytest.raises(ValidationError):
        PreferenceUpdate(recent_queries=tuple(f"query-{index}" for index in range(11)))


@pytest.mark.asyncio
async def test_best_effort_update_logs_and_does_not_raise(caplog) -> None:
    class FailedStore:
        async def aget(self, namespace, key):
            raise OSError("store unavailable")

        async def aput(self, namespace, key, value):
            raise OSError("store unavailable")

    repository = UserPreferenceRepository(FailedStore())

    updated = await repository.update_best_effort(
        context("user-1"),
        PreferenceUpdate(preferred_language="zh-CN"),
    )

    assert updated is False
    assert "用户偏好自动更新失败" in caplog.text
