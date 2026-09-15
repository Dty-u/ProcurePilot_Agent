from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from procurepilot.business.enums import Currency, OrderAction, PartStatus, SupplierStatus, Unit
from procurepilot.business.schemas import (
    InventoryItemInput,
    OrderOperationInput,
    PartInput,
    PurchaseOrderItemInput,
    SupplierInput,
    SupplierQuotationInput,
)


def test_supplier_input_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SupplierInput(
            supplier_id="supplier-1",
            supplier_code="SUP-001",
            name="示例供应商",
            status=SupplierStatus.ACTIVE,
            unexpected="not-allowed",  # type: ignore[call-arg]
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_supplier_input_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        SupplierInput(
            supplier_id="supplier-1",
            supplier_code="SUP-001",
            name="示例供应商",
            status="enabled",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("field_name", ["unit_price", "minimum_order_quantity"])
def test_quotation_input_rejects_json_float(field_name: str) -> None:
    values = {
        "quotation_id": "quotation-1",
        "supplier_id": "supplier-1",
        "part_id": "part-1",
        "unit_price": "1.25",
        "currency": Currency.CNY,
        "minimum_order_quantity": "100",
        "unit": Unit.PIECE,
        "lead_time_days": 14,
        "valid_from": "2026-09-08T08:00:00+00:00",
        "valid_until": "2026-10-08T08:00:00+00:00",
        "source": "supplier-portal",
        "collected_at": "2026-09-08T08:00:00+00:00",
    }
    values[field_name] = 1.25

    with pytest.raises(ValidationError) as exc_info:
        SupplierQuotationInput.model_validate(values)

    assert exc_info.value.errors()[0]["loc"] == (field_name,)


def test_quotation_input_accepts_decimal_strings_and_normalizes_time() -> None:
    quotation = SupplierQuotationInput.model_validate(
        {
            "quotation_id": "quotation-1",
            "supplier_id": "supplier-1",
            "part_id": "part-1",
            "unit_price": "1.25",
            "currency": "CNY",
            "minimum_order_quantity": Decimal("100"),
            "unit": "piece",
            "lead_time_days": 14,
            "valid_from": "2026-09-08T16:00:00+08:00",
            "valid_until": "2026-10-08T08:00:00+00:00",
            "source": "supplier-portal",
            "collected_at": "2026-09-08T08:00:00+00:00",
        }
    )

    assert quotation.unit_price == Decimal("1.25")
    assert quotation.minimum_order_quantity == Decimal("100")
    assert quotation.valid_from == datetime(2026, 9, 8, 8, 0, tzinfo=UTC)


def test_quotation_input_reports_naive_datetime_at_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SupplierQuotationInput.model_validate(
            {
                "quotation_id": "quotation-1",
                "supplier_id": "supplier-1",
                "part_id": "part-1",
                "unit_price": "1.25",
                "currency": "CNY",
                "minimum_order_quantity": "100",
                "unit": "piece",
                "lead_time_days": 14,
                "valid_from": "2026-09-08T08:00:00",
                "valid_until": "2026-10-08T08:00:00+00:00",
                "source": "supplier-portal",
                "collected_at": "2026-09-08T08:00:00+00:00",
            }
        )

    assert exc_info.value.errors()[0]["loc"] == ("valid_from",)


def test_order_item_input_rejects_zero_quantity() -> None:
    with pytest.raises(ValidationError):
        PurchaseOrderItemInput(
            part_id="part-1",
            quantity="0",
            unit=Unit.PIECE,
            unit_price="1.25",
            currency=Currency.CNY,
            quotation_id="quotation-1",
        )


def test_all_external_input_schemas_accept_valid_minimum_payloads() -> None:
    supplier = SupplierInput(
        supplier_id="supplier-1",
        supplier_code="SUP-001",
        name="示例供应商",
        status=SupplierStatus.ACTIVE,
    )
    part = PartInput(
        part_id="part-1",
        part_code="PART-001",
        name="示例物料",
        specification="M8",
        unit=Unit.PIECE,
        status=PartStatus.ACTIVE,
    )
    inventory = InventoryItemInput(
        inventory_id="inventory-1",
        part_id="part-1",
        warehouse_code="WH-01",
        unit=Unit.PIECE,
        on_hand_quantity="100",
        reserved_quantity="20",
        safety_stock="10",
    )
    operation = OrderOperationInput(
        action=OrderAction.CREATE,
        supplier_id="supplier-1",
        currency=Currency.CNY,
        items=(
            PurchaseOrderItemInput(
                part_id="part-1",
                quantity="10",
                unit=Unit.PIECE,
                unit_price="1.25",
                currency=Currency.CNY,
                quotation_id="quotation-1",
            ),
        ),
        idempotency_key="request-1",
    )

    assert supplier.status is SupplierStatus.ACTIVE
    assert part.unit is Unit.PIECE
    assert inventory.on_hand_quantity == Decimal("100")
    assert operation.action is OrderAction.CREATE
