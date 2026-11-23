"""物料 MCP 工具适配器。"""

import asyncio
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from mcp_server.context import ToolCallerContext
from mcp_server.error_mapper import error_envelope
from mcp_server.schemas import StrictInput, ToolEnvelope
from procurepilot.business.entities import Part
from procurepilot.business.enums import PartStatus, Unit
from procurepilot.business.errors import DomainValidationError, PermissionDeniedError
from procurepilot.business.query_models import PartSearchCriteria


class PartQueryInput(StrictInput):
    keyword: str | None = Field(default=None, min_length=1)
    status: PartStatus | None = None
    unit: Unit | None = None
    limit: int = Field(default=20, ge=1, le=50)


class PartBySupplierInput(StrictInput):
    supplier_id: str = Field(min_length=1, max_length=128)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    limit: int = Field(default=20, ge=1, le=50)


class PartResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    part_id: str
    part_code: str
    name: str
    specification: str
    unit: Unit
    status: PartStatus


class PartSearcher(Protocol):
    async def search(self, criteria: PartSearchCriteria) -> list[Part]: ...

    async def find_by_supplier(
        self, supplier_id: str, *, at: datetime, limit: int
    ) -> list[Part]: ...


def _authorize(caller: ToolCallerContext) -> None:
    if not caller.roles.intersection({"procurement_reader", "admin"}):
        raise PermissionDeniedError("role required: procurement_reader")


def _validate_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{field_name} must be timezone-aware")


async def part_query(
    request: PartQueryInput,
    *,
    service: PartSearcher,
    caller: ToolCallerContext,
    timeout_seconds: float,
) -> ToolEnvelope[list[PartResult]]:
    try:
        _authorize(caller)
        entities = await asyncio.wait_for(
            service.search(
                PartSearchCriteria(
                    keyword=request.keyword,
                    status=request.status,
                    unit=request.unit,
                    limit=request.limit,
                )
            ),
            timeout_seconds,
        )
        data = [PartResult.model_validate(entity, from_attributes=True) for entity in entities]
        return ToolEnvelope(ok=True, data=data[: request.limit], error=None, trace_id=caller.trace_id)
    except Exception as error:
        return error_envelope(error, trace_id=caller.trace_id)  # type: ignore[return-value]


async def part_by_supplier(
    request: PartBySupplierInput,
    *,
    service: PartSearcher,
    caller: ToolCallerContext,
    timeout_seconds: float,
) -> ToolEnvelope[list[PartResult]]:
    try:
        _authorize(caller)
        _validate_aware(request.at, "at")
        entities = await asyncio.wait_for(
            service.find_by_supplier(request.supplier_id, at=request.at, limit=request.limit),
            timeout_seconds,
        )
        data = [PartResult.model_validate(entity, from_attributes=True) for entity in entities]
        return ToolEnvelope(ok=True, data=data[: request.limit], error=None, trace_id=caller.trace_id)
    except Exception as error:
        return error_envelope(error, trace_id=caller.trace_id)  # type: ignore[return-value]
