from decimal import Decimal

import pytest

from procurepilot.business.entities import PurchaseOrder, PurchaseOrderItem
from procurepilot.business.enums import Currency, OrderStatus, Unit
from procurepilot.business.errors import (
    CurrencyMismatchError,
    DomainValidationError,
    ImmutableOrderError,
    InvalidOrderStateError,
)
from procurepilot.business.value_objects import Money, PositiveQuantity


def make_item(
    item_id: str,
    *,
    quantity: str = "1",
    unit_price: str = "1.00",
    currency: Currency = Currency.CNY,
) -> PurchaseOrderItem:
    return PurchaseOrderItem(
        order_item_id=item_id,
        part_id=f"part-{item_id}",
        quantity=PositiveQuantity(Decimal(quantity), Unit.PIECE),
        unit_price=Money(Decimal(unit_price), currency),
        quotation_id=f"quotation-{item_id}",
    )


def make_order(
    *items: PurchaseOrderItem,
    status: OrderStatus = OrderStatus.DRAFT,
) -> PurchaseOrder:
    return PurchaseOrder(
        order_id="order-1",
        order_no="PO-20260908-001",
        supplier_id="supplier-1",
        status=status,
        currency=Currency.CNY,
        items=items or (make_item("1"),),
        idempotency_key="request-1",
    )


def test_order_item_line_amount_is_calculated_exactly() -> None:
    item = make_item("1", quantity="0.3", unit_price="0.1")

    assert item.line_amount == Money(Decimal("0.03"), Currency.CNY)


def test_order_total_is_calculated_from_multiple_items() -> None:
    order = make_order(
        make_item("1", unit_price="0.1"),
        make_item("2", unit_price="0.2"),
    )

    assert order.total_amount == Money(Decimal("0.30"), Currency.CNY)


def test_order_rejects_items_with_different_currency() -> None:
    with pytest.raises(CurrencyMismatchError, match="currency"):
        make_order(make_item("1", currency=Currency.USD))


def test_order_rejects_empty_items() -> None:
    with pytest.raises(DomainValidationError, match="at least one item"):
        PurchaseOrder(
            order_id="order-1",
            order_no="PO-20260908-001",
            supplier_id="supplier-1",
            status=OrderStatus.DRAFT,
            currency=Currency.CNY,
            items=(),
            idempotency_key="request-1",
        )


def test_caller_cannot_supply_forged_total_amount() -> None:
    with pytest.raises(TypeError):
        PurchaseOrder(
            order_id="order-1",
            order_no="PO-20260908-001",
            supplier_id="supplier-1",
            status=OrderStatus.DRAFT,
            currency=Currency.CNY,
            items=(make_item("1"),),
            idempotency_key="request-1",
            total_amount=Money(Decimal("0.01"), Currency.CNY),  # type: ignore[call-arg]
        )


def test_draft_order_cannot_transition_directly_to_created() -> None:
    with pytest.raises(InvalidOrderStateError, match="draft.*created"):
        make_order().transition_to(OrderStatus.CREATED)


def test_order_follows_approval_state_machine() -> None:
    pending = make_order().transition_to(OrderStatus.PENDING_APPROVAL)
    approved = pending.transition_to(OrderStatus.APPROVED)
    created = approved.transition_to(OrderStatus.CREATED)
    cancelled = created.transition_to(OrderStatus.CANCELLED)

    assert cancelled.status is OrderStatus.CANCELLED


def test_pending_order_can_be_rejected() -> None:
    rejected = make_order().transition_to(OrderStatus.PENDING_APPROVAL).transition_to(
        OrderStatus.REJECTED
    )

    assert rejected.status is OrderStatus.REJECTED


def test_cancelled_order_cannot_replace_items() -> None:
    cancelled = make_order(status=OrderStatus.CREATED).transition_to(OrderStatus.CANCELLED)

    with pytest.raises(ImmutableOrderError, match="cancelled"):
        cancelled.replace_items((make_item("replacement"),))
