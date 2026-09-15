"""白名单用户偏好模型及 LangGraph Store 适配。"""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from agent.context import ProcurementContext
from procurepilot.business.enums import Currency

LOGGER = logging.getLogger(__name__)
_PREFERENCE_KEY = "preferences"
_SupplierId = Annotated[StrictStr, Field(min_length=1, max_length=128)]
_RecentQuery = Annotated[StrictStr, Field(min_length=1, max_length=500)]


class PreferenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UserPreferences(PreferenceModel):
    preferred_output: Literal["concise", "detailed", "table"] | None = None
    preferred_chart_type: Literal["none", "bar", "line", "pie"] | None = None
    preferred_currency: Currency | None = None
    preferred_language: StrictStr | None = Field(default=None, min_length=2, max_length=16)
    recent_suppliers: tuple[_SupplierId, ...] = Field(default=(), max_length=10)
    recent_queries: tuple[_RecentQuery, ...] = Field(default=(), max_length=10)


class PreferenceUpdate(PreferenceModel):
    preferred_output: Literal["concise", "detailed", "table"] | None = None
    preferred_chart_type: Literal["none", "bar", "line", "pie"] | None = None
    preferred_currency: Currency | None = None
    preferred_language: StrictStr | None = Field(default=None, min_length=2, max_length=16)
    recent_suppliers: tuple[_SupplierId, ...] | None = Field(default=None, max_length=10)
    recent_queries: tuple[_RecentQuery, ...] | None = Field(default=None, max_length=10)


class PreferenceStore(Protocol):
    async def aget(self, namespace: tuple[str, ...], key: str) -> Any: ...

    async def aput(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: dict[str, Any],
    ) -> None: ...


class UserPreferenceRepository:
    """所有 namespace 均从可信上下文派生，调用方不能指定其他用户。"""

    def __init__(self, store: PreferenceStore) -> None:
        self._store = store

    async def get(self, context: ProcurementContext) -> UserPreferences:
        item = await self._store.aget(self._namespace(context), _PREFERENCE_KEY)
        if item is None:
            return UserPreferences()
        return UserPreferences.model_validate(item.value)

    async def update(
        self,
        context: ProcurementContext,
        update: PreferenceUpdate,
    ) -> UserPreferences:
        current = await self.get(context)
        values = current.model_dump()
        values.update(update.model_dump(exclude_unset=True, exclude_none=True))
        preferences = UserPreferences.model_validate(values)
        await self._store.aput(
            self._namespace(context),
            _PREFERENCE_KEY,
            preferences.model_dump(mode="json"),
        )
        return preferences

    async def update_best_effort(
        self,
        context: ProcurementContext,
        update: PreferenceUpdate,
    ) -> bool:
        """自动偏好写入允许降级，但不会吞掉身份隔离错误。"""

        try:
            await self.update(context, update)
        except (PermissionError, ValueError):
            raise
        except Exception:
            LOGGER.warning(
                "用户偏好自动更新失败",
                extra={"trace_id": context.trace_id, "thread_id": context.thread_id},
            )
            return False
        return True

    @staticmethod
    def _namespace(context: ProcurementContext) -> tuple[str, ...]:
        user_scope = hashlib.sha256(context.user_id.encode("utf-8")).hexdigest()
        return "procurepilot", "user_preferences", user_scope
