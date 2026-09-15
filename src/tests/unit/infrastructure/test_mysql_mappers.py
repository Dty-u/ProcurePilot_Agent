from datetime import UTC, datetime, timedelta, timezone, tzinfo
from decimal import Decimal

from procurepilot.business.entities import PurchaseOrderItem, SupplierQuotation
from procurepilot.business.enums import Currency, OrderAction, Unit
from procurepilot.business.order_operations import CancelOrderPayload, OrderOperation
from procurepilot.business.value_objects import Money, PositiveQuantity
from procurepilot.infrastructure.mysql_repositories import (
    operation_from_orm,
    operation_to_orm,
    purchase_order_item_from_orm,
    purchase_order_item_to_orm,
    quotation_from_orm,
    quotation_to_orm,
)


def test_quotation_mapper_preserves_decimal_precision_and_restores_utc() -> None:
    quotation = SupplierQuotation(
        quotation_id="quote-1",
        supplier_id="supplier-1",
        part_id="part-1",
        unit_price=Money(Decimal("12.3456"), Currency.CNY),
        minimum_order_quantity=PositiveQuantity(Decimal("1.234567"), Unit.KILOGRAM),
        lead_time_days=4,
        valid_from=datetime(2026, 9, 8, 8, tzinfo=UTC),
        valid_until=datetime(2026, 9, 10, 8, tzinfo=UTC),
        source="test",
        collected_at=datetime(2026, 9, 8, 16, tzinfo=timezone_plus_eight()),
    )

    row = quotation_to_orm(quotation)
    restored = quotation_from_orm(row)

    assert row.collected_at.tzinfo is None
    assert row.collected_at == datetime(2026, 9, 8, 8)
    assert restored == quotation
    assert restored.collected_at.tzinfo is UTC


def test_order_item_mapper_keeps_quantity_unit_and_money_currency() -> None:
    item = PurchaseOrderItem(
        order_item_id="item-1",
        part_id="part-1",
        quantity=PositiveQuantity(Decimal("3.125000"), Unit.KILOGRAM),
        unit_price=Money(Decimal("7.8912"), Currency.USD),
        quotation_id="quote-1",
    )

    restored = purchase_order_item_from_orm(
        purchase_order_item_to_orm(item, order_id="order-1")
    )

    assert restored == item


def test_order_operation_mapper_preserves_bound_payload_and_utc_scope() -> None:
    operation = OrderOperation.create(
        operation_id="operation-1",
        action=OrderAction.CANCEL,
        user_id="user-1",
        thread_id="thread-1",
        payload=CancelOrderPayload(target_order_id="order-1", expected_version=2),
        created_at=datetime(2026, 9, 9, 8, tzinfo=UTC),
        expires_at=datetime(2026, 9, 9, 9, tzinfo=UTC),
    )

    row = operation_to_orm(operation)
    restored = operation_from_orm(row)

    assert row.created_at.tzinfo is None
    assert restored == operation


def timezone_plus_eight() -> tzinfo:
    return timezone(timedelta(hours=8))
