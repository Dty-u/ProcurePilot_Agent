"""Trusted runtime context supplied to Agent tools by the application."""

from pydantic import BaseModel, ConfigDict, Field

from mcp_server.context import SAFE_IDENTIFIER, ToolRole


class ProcurementContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    user_id: str = Field(pattern=SAFE_IDENTIFIER)
    username: str = Field(default="unknown", min_length=1, max_length=128)
    thread_id: str = Field(default="unknown-thread", pattern=SAFE_IDENTIFIER)
    roles: frozenset[ToolRole] = Field(min_length=1)
    trace_id: str = Field(pattern=SAFE_IDENTIFIER)
    language: str = Field(default="zh-CN", min_length=2, max_length=16)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
