from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from procurepilot.business.entities import (
    InventoryItem,
    OperationAudit,
    Part,
    Supplier,
    SupplierQuotation,
)
from procurepilot.business.enums import Currency, PartStatus, SupplierStatus, Unit
from procurepilot.business.errors import DomainValidationError, InactiveEntityError
from procurepilot.business.value_objects import Money, PositiveQuantity

NOW = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)


def make_supplier(status: SupplierStatus = SupplierStatus.ACTIVE) -> Supplier:
    return Supplier(
        supplier_id="supplier-1",
        supplier_code="SUP-001",
        name="示例供应商",
        status=status,
    )


def make_part(status: PartStatus = PartStatus.ACTIVE) -> Part:
    return Part(
        part_id="part-1",
        part_code="PART-001",
        name="示例物料",
        specification="M8",
        unit=Unit.PIECE,
        status=status,
    )


def make_quotation(
    *,
    valid_from: datetime = NOW - timedelta(days=1),
    valid_until: datetime = NOW + timedelta(days=1),
) -> SupplierQuotation:
    return SupplierQuotation(
        quotation_id="quotation-1",
        supplier_id="supplier-1",
        part_id="part-1",
        unit_price=Money(Decimal("1.25"), Currency.CNY),
        minimum_order_quantity=PositiveQuantity(Decimal("100"), Unit.PIECE),
        lead_time_days=14,
        valid_from=valid_from,
        valid_until=valid_until,
        source="supplier-portal",
        collected_at=NOW,
    )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [("supplier_id", ""), ("supplier_code", "  "), ("name", "")],
)
def test_supplier_requires_non_empty_identity_fields(
    field_name: str,
    field_value: str,
) -> None:
    values = {
        "supplier_id": "supplier-1",
        "supplier_code": "SUP-001",
        "name": "示例供应商",
        "status": SupplierStatus.ACTIVE,
    }
    values[field_name] = field_value

    with pytest.raises(DomainValidationError, match=field_name):
        Supplier(**values)  # type: ignore[arg-type]


def test_inactive_supplier_is_not_procurement_eligible() -> None:
    with pytest.raises(InactiveEntityError, match="supplier"):
        make_supplier(SupplierStatus.INACTIVE).ensure_procurement_eligible()


def test_inactive_part_is_not_procurement_eligible() -> None:
    with pytest.raises(InactiveEntityError, match="part"):
        make_part(PartStatus.INACTIVE).ensure_procurement_eligible()


def test_quotation_is_invalid_after_expiration() -> None:
    quotation = make_quotation(valid_until=NOW)

    assert quotation.is_valid_at(NOW + timedelta(microseconds=1)) is False


def test_quotation_is_invalid_before_effective_time() -> None:
    quotation = make_quotation(valid_from=NOW, valid_until=NOW + timedelta(days=1))

    assert quotation.is_valid_at(NOW - timedelta(microseconds=1)) is False


def test_quotation_is_valid_at_time_boundaries() -> None:
    quotation = make_quotation(valid_from=NOW, valid_until=NOW + timedelta(days=1))

    assert quotation.is_valid_at(NOW) is True
    assert quotation.is_valid_at(NOW + timedelta(days=1)) is True


def test_quotation_requires_minimum_order_quantity() -> None:
    quotation = make_quotation()

    assert quotation.supports_quantity(PositiveQuantity(Decimal("99"), Unit.PIECE)) is False
    assert quotation.supports_quantity(PositiveQuantity(Decimal("100"), Unit.PIECE)) is True
    assert quotation.supports_quantity(PositiveQuantity(Decimal("100"), Unit.KILOGRAM)) is False


def test_inventory_available_quantity_is_derived() -> None:
    inventory = InventoryItem(
        inventory_id="inventory-1",
        part_id="part-1",
        warehouse_code="WH-01",
        unit=Unit.PIECE,
        on_hand_quantity=Decimal("100"),
        reserved_quantity=Decimal("35.5"),
        safety_stock=Decimal("20"),
    )

    assert inventory.available_quantity == Decimal("64.5")


def test_inventory_rejects_caller_supplied_available_quantity() -> None:
    with pytest.raises(TypeError):
        InventoryItem(
            inventory_id="inventory-1",
            part_id="part-1",
            warehouse_code="WH-01",
            unit=Unit.PIECE,
            on_hand_quantity=Decimal("100"),
            reserved_quantity=Decimal("20"),
            safety_stock=Decimal("20"),
            available_quantity=Decimal("999"),  # type: ignore[call-arg]
        )


def test_operation_audit_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(DomainValidationError, match="occurred_at"):
        OperationAudit(
            audit_id="audit-1",
            trace_id="trace-1",
            user_id="user-1",
            action="quotation.viewed",
            object_type="quotation",
            object_id="quotation-1",
            parameter_summary="quotation_id=quotation-1",
            result="success",
            occurred_at=datetime(2026, 9, 8, 8, 0),
        )
