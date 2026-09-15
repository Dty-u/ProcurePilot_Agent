"""Supplier and quotation MCP tool adapters."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mcp_server.context import ToolCallerContext
from mcp_server.error_mapper import error_envelope
from mcp_server.schemas import StrictInput, ToolEnvelope
from procurepilot.business.entities import Supplier, SupplierQuotation
from procurepilot.business.enums import Currency, SupplierStatus, Unit
from procurepilot.business.errors import DomainValidationError, PermissionDeniedError
from procurepilot.business.query_models import QuotationSearchCriteria, SupplierSearchCriteria
from procurepilot.business.value_objects import PositiveQuantity


class SupplierQueryInput(StrictInput):
    keyword: str | None = Field(default=None, min_length=1)
    status: SupplierStatus | None = None
    limit: int = Field(default=20, ge=1, le=50)


class QuotationQueryInput(StrictInput):
    part_id: str | None = Field(default=None, min_length=1, max_length=128)
    supplier_id: str | None = Field(default=None, min_length=1, max_length=128)
    currency: Currency | None = None
    unit: Unit | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_quantity_unit_pair(self) -> "QuotationQueryInput":
        if (self.quantity is None) != (self.unit is None):
            raise ValueError("quantity and unit must be provided together")
        return self


class SupplierResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    supplier_id: str
    supplier_code: str
    name: str
    status: SupplierStatus
    quality_score: Decimal | None
    delivery_score: Decimal | None
    version: int


class QuotationResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    quotation_id: str
    supplier_id: str
    part_id: str
    unit_price: Decimal
    currency: Currency
    minimum_order_quantity: Decimal
    unit: Unit
    lead_time_days: int
    source: str
    collected_at: datetime
    valid_from: datetime
    valid_until: datetime


class SupplierSearcher(Protocol):
    async def search(self, criteria: SupplierSearchCriteria) -> list[Supplier]: ...


class QuotationSearcher(Protocol):
    async def find_valid_quotes(
        self, criteria: QuotationSearchCriteria, at: datetime
    ) -> list[SupplierQuotation]: ...


def _authorize(caller: ToolCallerContext) -> None:
    if not caller.roles.intersection({"procurement_reader", "admin"}):
        raise PermissionDeniedError("role required: procurement_reader")


def _validate_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{field_name} must be timezone-aware")


async def supplier_query(
    request: SupplierQueryInput,
    *,
    service: SupplierSearcher,
    caller: ToolCallerContext,
    timeout_seconds: float,
) -> ToolEnvelope[list[SupplierResult]]:
    try:
        _authorize(caller)
        entities = await asyncio.wait_for(
            service.search(
                SupplierSearchCriteria(
                    keyword=request.keyword, status=request.status, limit=request.limit
                )
            ),
            timeout_seconds,
        )
        data = [SupplierResult.model_validate(entity, from_attributes=True) for entity in entities]
        return ToolEnvelope(ok=True, data=data[: request.limit], error=None, trace_id=caller.trace_id)
    except Exception as error:
        return error_envelope(error, trace_id=caller.trace_id)  # type: ignore[return-value]


async def quotation_query(
    request: QuotationQueryInput,
    *,
    service: QuotationSearcher,
    caller: ToolCallerContext,
    timeout_seconds: float,
) -> ToolEnvelope[list[QuotationResult]]:
    try:
        _authorize(caller)
        _validate_aware(request.at, "at")
        quantity = (
            PositiveQuantity(request.quantity, request.unit)
            if request.quantity is not None and request.unit is not None
            else None
        )
        entities = await asyncio.wait_for(
            service.find_valid_quotes(
                QuotationSearchCriteria(
                    part_id=request.part_id,
                    supplier_id=request.supplier_id,
                    currency=request.currency,
                    unit=request.unit,
                    quantity=quantity,
                    limit=request.limit,
                ),
                request.at,
            ),
            timeout_seconds,
        )
        data = [
            QuotationResult(
                quotation_id=entity.quotation_id,
                supplier_id=entity.supplier_id,
                part_id=entity.part_id,
                unit_price=entity.unit_price.amount,
                currency=entity.unit_price.currency,
                minimum_order_quantity=entity.minimum_order_quantity.amount,
                unit=entity.minimum_order_quantity.unit,
                lead_time_days=entity.lead_time_days,
                source=entity.source,
                collected_at=entity.collected_at,
                valid_from=entity.valid_from,
                valid_until=entity.valid_until,
            )
            for entity in entities[: request.limit]
        ]
        return ToolEnvelope(ok=True, data=data, error=None, trace_id=caller.trace_id)
    except Exception as error:
        return error_envelope(error, trace_id=caller.trace_id)  # type: ignore[return-value]
