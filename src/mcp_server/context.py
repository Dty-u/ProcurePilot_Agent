"""MCP 适配器的可信调用方身份契约。"""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from procurepilot.business.errors import PermissionDeniedError

ToolRole = Literal[
    "procurement_reader",
    "order_reader",
    "buyer",
    "order_executor",
    "admin",
]
SAFE_IDENTIFIER = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class ToolCallerContext(BaseModel):
    """由服务端提供的身份，绝不作为业务工具参数接收。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    user_id: str = Field(pattern=SAFE_IDENTIFIER)
    roles: frozenset[ToolRole] = Field(min_length=1)
    trace_id: str = Field(pattern=SAFE_IDENTIFIER)
    thread_id: str | None = Field(default=None, pattern=SAFE_IDENTIFIER)


class CallerContextProvider(Protocol):
    async def get_context(self) -> ToolCallerContext: ...


class MissingCallerContextProvider:
    """在配置可信认证适配器之前使用的安全默认值。"""

    async def get_context(self) -> ToolCallerContext:
        raise PermissionDeniedError("trusted caller context is not configured")
