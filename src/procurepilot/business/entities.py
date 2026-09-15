"""Procurement entities with deterministic domain invariants."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from procurepilot.business.enums import Currency, OrderStatus, PartStatus, SupplierStatus, Unit
from procurepilot.business.errors import (
    CurrencyMismatchError,
    DomainValidationError,
    ImmutableOrderError,
    InactiveEntityError,
)
from procurepilot.business.policies.order_policy import ensure_order_transition
from procurepilot.business.value_objects import Money, PositiveQuantity, ensure_utc


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty")


def _require_decimal(value: Decimal, field_name: str, *, allow_zero: bool = True) -> None:
    if not isinstance(value, Decimal):
        raise DomainValidationError(f"{field_name} must be a Decimal")
    if value < 0 or (not allow_zero and value == 0):
        comparison = "non-negative" if allow_zero else "greater than zero"
        raise DomainValidationError(f"{field_name} must be {comparison}")


@dataclass(frozen=True, slots=True)
class Supplier:
    supplier_id: str
    supplier_code: str
    name: str
    status: SupplierStatus
    quality_score: Decimal | None = None
    delivery_score: Decimal | None = None
    version: int = 1

    def __post_init__(self) -> None:
        _require_text(self.supplier_id, "supplier_id")
        _require_text(self.supplier_code, "supplier_code")
        _require_text(self.name, "name")
        if not isinstance(self.status, SupplierStatus):
            raise DomainValidationError("status must be a SupplierStatus")
        if self.version < 1:
            raise DomainValidationError("version must be greater than zero")

    def ensure_procurement_eligible(self) -> None:
        if self.status is not SupplierStatus.ACTIVE:
            raise InactiveEntityError(f"supplier {self.supplier_id} is inactive")


@dataclass(frozen=True, slots=True)
class Part:
    part_id: str
    part_code: str
    name: str
    specification: str
    unit: Unit
    status: PartStatus

    def __post_init__(self) -> None:
        _require_text(self.part_id, "part_id")
        _require_text(self.part_code, "part_code")
        _require_text(self.name, "name")
        _require_text(self.specification, "specification")
        if not isinstance(self.unit, Unit):
            raise DomainValidationError("unit must be a Unit")
        if not isinstance(self.status, PartStatus):
            raise DomainValidationError("status must be a PartStatus")

    def ensure_procurement_eligible(self) -> None:
        if self.status is not PartStatus.ACTIVE:
            raise InactiveEntityError(f"part {self.part_id} is inactive")


@dataclass(frozen=True, slots=True)
class SupplierQuotation:
    quotation_id: str
    supplier_id: str
    part_id: str
    unit_price: Money
    minimum_order_quantity: PositiveQuantity
    lead_time_days: int
    valid_from: datetime
    valid_until: datetime
    source: str
    collected_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.quotation_id, "quotation_id")
        _require_text(self.supplier_id, "supplier_id")
        _require_text(self.part_id, "part_id")
        _require_text(self.source, "source")
        if self.unit_price.amount <= 0:
            raise DomainValidationError("unit_price must be greater than zero")
        if self.lead_time_days < 0:
            raise DomainValidationError("lead_time_days must be non-negative")

        valid_from = ensure_utc(self.valid_from)
        valid_until = ensure_utc(self.valid_until)
        collected_at = ensure_utc(self.collected_at)
        if valid_until < valid_from:
            raise DomainValidationError("valid_until must not precede valid_from")
        object.__setattr__(self, "valid_from", valid_from)
        object.__setattr__(self, "valid_until", valid_until)
        object.__setattr__(self, "collected_at", collected_at)

    def is_valid_at(self, at: datetime) -> bool:
        checked_at = ensure_utc(at)
        return self.valid_from <= checked_at <= self.valid_until

    def supports_quantity(self, quantity: PositiveQuantity) -> bool:
        minimum = self.minimum_order_quantity
        return quantity.unit is minimum.unit and quantity.amount >= minimum.amount


@dataclass(frozen=True, slots=True)
class InventoryItem:
    inventory_id: str
    part_id: str
    warehouse_code: str
    unit: Unit
    on_hand_quantity: Decimal
    reserved_quantity: Decimal
    safety_stock: Decimal
    version: int = 1

    def __post_init__(self) -> None:
        _require_text(self.inventory_id, "inventory_id")
        _require_text(self.part_id, "part_id")
        _require_text(self.warehouse_code, "warehouse_code")
        if not isinstance(self.unit, Unit):
            raise DomainValidationError("unit must be a Unit")
        _require_decimal(self.on_hand_quantity, "on_hand_quantity")
        _require_decimal(self.reserved_quantity, "reserved_quantity")
        _require_decimal(self.safety_stock, "safety_stock")
        if self.reserved_quantity > self.on_hand_quantity:
            raise DomainValidationError("reserved_quantity must not exceed on_hand_quantity")
        if self.version < 1:
            raise DomainValidationError("version must be greater than zero")

    @property
    def available_quantity(self) -> Decimal:
        return self.on_hand_quantity - self.reserved_quantity


@dataclass(frozen=True, slots=True)
class PurchaseOrderItem:
    order_item_id: str
    part_id: str
    quantity: PositiveQuantity
    unit_price: Money
    quotation_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.order_item_id, "order_item_id")
        _require_text(self.part_id, "part_id")
        if self.quotation_id is not None:
            _require_text(self.quotation_id, "quotation_id")

    @property
    def line_amount(self) -> Money:
        return Money(self.unit_price.amount * self.quantity.amount, self.unit_price.currency)


@dataclass(frozen=True, slots=True)
class PurchaseOrder:
    order_id: str
    order_no: str
    supplier_id: str
    status: OrderStatus
    currency: Currency
    items: tuple[PurchaseOrderItem, ...]
    idempotency_key: str
    version: int = 1

    def __post_init__(self) -> None:
        _require_text(self.order_id, "order_id")
        _require_text(self.order_no, "order_no")
        _require_text(self.supplier_id, "supplier_id")
        _require_text(self.idempotency_key, "idempotency_key")
        if not isinstance(self.status, OrderStatus):
            raise DomainValidationError("status must be an OrderStatus")
        if not isinstance(self.currency, Currency):
            raise DomainValidationError("currency must be a Currency")

        items = tuple(self.items)
        if not items:
            raise DomainValidationError("Purchase order requires at least one item")
        if any(item.unit_price.currency is not self.currency for item in items):
            raise CurrencyMismatchError("Purchase order item currency must match order currency")
        if self.version < 1:
            raise DomainValidationError("version must be greater than zero")
        object.__setattr__(self, "items", items)

    @property
    def total_amount(self) -> Money:
        total = Money(Decimal("0"), self.currency)
        for item in self.items:
            total += item.line_amount
        return total

    def transition_to(self, target: OrderStatus) -> "PurchaseOrder":
        ensure_order_transition(self.status, target)
        return replace(self, status=target, version=self.version + 1)

    def replace_items(self, items: tuple[PurchaseOrderItem, ...]) -> "PurchaseOrder":
        if self.status is OrderStatus.CANCELLED:
            raise ImmutableOrderError("A cancelled order cannot be modified")
        return replace(self, items=items, version=self.version + 1)


@dataclass(frozen=True, slots=True)
class OperationAudit:
    audit_id: str
    trace_id: str
    user_id: str
    action: str
    object_type: str
    object_id: str
    parameter_summary: str
    result: str
    occurred_at: datetime
    approved_by: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "audit_id",
            "trace_id",
            "user_id",
            "action",
            "object_type",
            "object_id",
            "parameter_summary",
            "result",
        ):
            _require_text(getattr(self, field_name), field_name)
        try:
            occurred_at = ensure_utc(self.occurred_at)
        except ValueError as error:
            raise DomainValidationError("occurred_at must be timezone-aware") from error
        object.__setattr__(self, "occurred_at", occurred_at)
