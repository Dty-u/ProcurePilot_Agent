"""Stable response contracts shared by all MCP tools."""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

ToolErrorCode = Literal[
    "VALIDATION_ERROR",
    "NOT_FOUND",
    "CONFLICT",
    "PERMISSION_DENIED",
    "APPROVAL_REQUIRED",
    "DEPENDENCY_TIMEOUT",
    "INTERNAL_ERROR",
]


class StrictInput(BaseModel):
    """Base model for MCP JSON arguments that rejects unexpected fields."""

    model_config = ConfigDict(extra="forbid")


class ToolError(BaseModel):
    """A safe, machine-readable tool failure."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: ToolErrorCode
    message: str = Field(min_length=1, max_length=500)
    retryable: bool


DataT = TypeVar("DataT")


class ToolEnvelope(BaseModel, Generic[DataT]):
    """Invariant response envelope returned by every MCP tool."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    ok: bool
    data: DataT | None
    error: ToolError | None
    trace_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_success_failure_shape(self) -> "ToolEnvelope[DataT]":
        if self.ok and (self.data is None or self.error is not None):
            raise ValueError("successful tool responses require data and forbid error")
        if not self.ok and (self.data is not None or self.error is None):
            raise ValueError("failed tool responses require error and forbid data")
        return self
