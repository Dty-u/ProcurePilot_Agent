"""Explicit, validated query objects used by business services."""

from pydantic import BaseModel, ConfigDict, Field

from procurepilot.business.enums import Currency, OrderStatus, PartStatus, SupplierStatus, Unit
from procurepilot.business.value_objects import PositiveQuantity


class QueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class SupplierSearchCriteria(QueryModel):
    keyword: str | None = Field(default=None, min_length=1)
    status: SupplierStatus | None = None
    limit: int = Field(default=50, ge=1, le=100)


class PartSearchCriteria(QueryModel):
    keyword: str | None = Field(default=None, min_length=1)
    status: PartStatus | None = None
    unit: Unit | None = None
    limit: int = Field(default=50, ge=1, le=100)


class QuotationSearchCriteria(QueryModel):
    part_id: str | None = Field(default=None, min_length=1)
    supplier_id: str | None = Field(default=None, min_length=1)
    currency: Currency | None = None
    unit: Unit | None = None
    quantity: PositiveQuantity | None = None
    limit: int = Field(default=100, ge=1, le=500)


class InventorySearchCriteria(QueryModel):
    part_id: str | None = Field(default=None, min_length=1)
    warehouse_code: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=100, ge=1, le=500)


class OrderSearchCriteria(QueryModel):
    order_id: str | None = Field(default=None, min_length=1)
    order_no: str | None = Field(default=None, min_length=1)
    supplier_id: str | None = Field(default=None, min_length=1)
    status: OrderStatus | None = None
    limit: int = Field(default=50, ge=1, le=100)


class ComparisonRequest(QueryModel):
    part_id: str = Field(min_length=1)
    quantity: PositiveQuantity
    currency: Currency
