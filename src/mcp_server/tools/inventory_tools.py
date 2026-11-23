"""库存 MCP 工具适配器。"""

import asyncio
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from mcp_server.context import ToolCallerContext
from mcp_server.error_mapper import error_envelope
from mcp_server.schemas import StrictInput, ToolEnvelope
from procurepilot.business.entities import InventoryItem
from procurepilot.business.enums import Unit
from procurepilot.business.errors import PermissionDeniedError
from procurepilot.business.query_models import InventorySearchCriteria


class InventoryWarningInput(StrictInput):
    part_id: str | None = Field(default=None, min_length=1, max_length=128)
    warehouse_code: str | None = Field(default=None, min_length=1, max_length=128)
    limit: int = Field(default=20, ge=1, le=100)


class InventoryWarningResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    inventory_id: str
    part_id: str
    warehouse_code: str
    unit: Unit
    on_hand_quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    safety_stock: Decimal
    version: int


class InventorySearcher(Protocol):
    async def get_warnings(self, criteria: InventorySearchCriteria) -> list[InventoryItem]: ...


async def inventory_warning(
    request: InventoryWarningInput,
    *,
    service: InventorySearcher,
    caller: ToolCallerContext,
    timeout_seconds: float,
) -> ToolEnvelope[list[InventoryWarningResult]]:
    try:
        if not caller.roles.intersection({"procurement_reader", "admin"}):
            raise PermissionDeniedError("role required: procurement_reader")
        entities = await asyncio.wait_for(
            service.get_warnings(
                InventorySearchCriteria(
                    part_id=request.part_id,
                    warehouse_code=request.warehouse_code,
                    limit=request.limit,
                )
            ),
            timeout_seconds,
        )
        data = [
            InventoryWarningResult(
                inventory_id=entity.inventory_id,
                part_id=entity.part_id,
                warehouse_code=entity.warehouse_code,
                unit=entity.unit,
                on_hand_quantity=entity.on_hand_quantity,
                reserved_quantity=entity.reserved_quantity,
                available_quantity=entity.available_quantity,
                safety_stock=entity.safety_stock,
                version=entity.version,
            )
            for entity in entities[: request.limit]
        ]
        return ToolEnvelope(ok=True, data=data, error=None, trace_id=caller.trace_id)
    except Exception as error:
        return error_envelope(error, trace_id=caller.trace_id)  # type: ignore[return-value]
