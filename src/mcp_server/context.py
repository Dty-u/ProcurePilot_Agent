"""Trusted caller identity contracts for the MCP adapter."""

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
    """Server-provided identity; never accepted as a business tool argument."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    user_id: str = Field(pattern=SAFE_IDENTIFIER)
    roles: frozenset[ToolRole] = Field(min_length=1)
    trace_id: str = Field(pattern=SAFE_IDENTIFIER)
    thread_id: str | None = Field(default=None, pattern=SAFE_IDENTIFIER)


class CallerContextProvider(Protocol):
    async def get_context(self) -> ToolCallerContext: ...


class MissingCallerContextProvider:
    """Secure default used until a trusted authentication adapter is configured."""

    async def get_context(self) -> ToolCallerContext:
        raise PermissionDeniedError("trusted caller context is not configured")
