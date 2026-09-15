"""Strict Pydantic schemas for untrusted procurement input."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from procurepilot.business.enums import (
    Currency,
    OrderAction,
    PartStatus,
    SupplierStatus,
    Unit,
)
from procurepilot.business.value_objects import ensure_utc


def _require_decimal_input(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, (str, Decimal)):
        raise ValueError("Decimal fields accept only strings or Decimal values")
    return value


NonEmptyText = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]
DecimalInput = Annotated[Decimal, BeforeValidator(_require_decimal_input)]
PositiveDecimalInput = Annotated[DecimalInput, Field(gt=0)]
NonNegativeDecimalInput = Annotated[DecimalInput, Field(ge=0)]
AwareDatetime = Annotated[datetime, AfterValidator(ensure_utc)]


class StrictInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SupplierInput(StrictInputModel):
    supplier_id: NonEmptyText
    supplier_code: NonEmptyText
    name: NonEmptyText
    status: SupplierStatus
    quality_score: NonNegativeDecimalInput | None = None
    delivery_score: NonNegativeDecimalInput | None = None
    version: int = Field(default=1, gt=0)


class PartInput(StrictInputModel):
    part_id: NonEmptyText
    part_code: NonEmptyText
    name: NonEmptyText
    specification: NonEmptyText
    unit: Unit
    status: PartStatus


class SupplierQuotationInput(StrictInputModel):
    quotation_id: NonEmptyText
    supplier_id: NonEmptyText
    part_id: NonEmptyText
    unit_price: PositiveDecimalInput
    currency: Currency
    minimum_order_quantity: PositiveDecimalInput
    unit: Unit
    lead_time_days: int = Field(ge=0)
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    source: NonEmptyText
    collected_at: AwareDatetime

    @model_validator(mode="after")
    def validate_validity_window(self) -> "SupplierQuotationInput":
        if self.valid_until < self.valid_from:
            raise ValueError("valid_until must not precede valid_from")
        return self


class InventoryItemInput(StrictInputModel):
    inventory_id: NonEmptyText
    part_id: NonEmptyText
    warehouse_code: NonEmptyText
    unit: Unit
    on_hand_quantity: NonNegativeDecimalInput
    reserved_quantity: NonNegativeDecimalInput
    safety_stock: NonNegativeDecimalInput
    version: int = Field(default=1, gt=0)

    @model_validator(mode="after")
    def validate_reservation(self) -> "InventoryItemInput":
        if self.reserved_quantity > self.on_hand_quantity:
            raise ValueError("reserved_quantity must not exceed on_hand_quantity")
        return self


class PurchaseOrderItemInput(StrictInputModel):
    part_id: NonEmptyText
    quantity: PositiveDecimalInput
    unit: Unit
    unit_price: PositiveDecimalInput
    currency: Currency
    quotation_id: NonEmptyText | None = None


class OrderOperationInput(StrictInputModel):
    action: OrderAction
    order_id: NonEmptyText | None = None
    supplier_id: NonEmptyText | None = None
    currency: Currency | None = None
    items: tuple[PurchaseOrderItemInput, ...] = ()
    idempotency_key: NonEmptyText | None = None
