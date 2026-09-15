from decimal import Decimal

import pytest

from procurepilot.business.entities import PurchaseOrder, PurchaseOrderItem, Supplier
from procurepilot.business.enums import Currency, OrderStatus, SupplierStatus, Unit
from procurepilot.business.errors import ConflictError
from procurepilot.business.in_memory import InMemoryDatabase, InMemoryUnitOfWork
from procurepilot.business.value_objects import Money, PositiveQuantity


def make_supplier(supplier_id: str = "supplier-1") -> Supplier:
    return Supplier(
        supplier_id=supplier_id,
        supplier_code=f"SUP-{supplier_id}",
        name="示例供应商",
        status=SupplierStatus.ACTIVE,
    )


def make_order(
    order_id: str = "order-1",
    *,
    idempotency_key: str = "request-1",
) -> PurchaseOrder:
    item = PurchaseOrderItem(
        order_item_id=f"item-{order_id}",
        part_id="part-1",
        quantity=PositiveQuantity(Decimal("10"), Unit.PIECE),
        unit_price=Money(Decimal("1.25"), Currency.CNY),
        quotation_id="quotation-1",
    )
    return PurchaseOrder(
        order_id=order_id,
        order_no=f"PO-{order_id}",
        supplier_id="supplier-1",
        status=OrderStatus.DRAFT,
        currency=Currency.CNY,
        items=(item,),
        idempotency_key=idempotency_key,
    )


@pytest.mark.asyncio
async def test_uncommitted_changes_are_rolled_back_on_exit() -> None:
    database = InMemoryDatabase()

    async with InMemoryUnitOfWork(database) as uow:
        await uow.suppliers.add(make_supplier())

    async with InMemoryUnitOfWork(database) as verification:
        assert await verification.suppliers.get_by_id("supplier-1") is None


@pytest.mark.asyncio
async def test_exception_rolls_back_working_changes() -> None:
    database = InMemoryDatabase()

    with pytest.raises(RuntimeError, match="boom"):
        async with InMemoryUnitOfWork(database) as uow:
            await uow.suppliers.add(make_supplier())
            raise RuntimeError("boom")

    async with InMemoryUnitOfWork(database) as verification:
        assert await verification.suppliers.get_by_id("supplier-1") is None


@pytest.mark.asyncio
async def test_committed_changes_are_visible_to_new_unit_of_work() -> None:
    database = InMemoryDatabase()

    async with InMemoryUnitOfWork(database) as uow:
        await uow.suppliers.add(make_supplier())
        await uow.commit()

    async with InMemoryUnitOfWork(database) as verification:
        stored = await verification.suppliers.get_by_id("supplier-1")

    assert stored == make_supplier()


@pytest.mark.asyncio
async def test_returned_entity_cannot_mutate_repository_state_by_shared_reference() -> None:
    database = InMemoryDatabase()
    async with InMemoryUnitOfWork(database) as uow:
        await uow.suppliers.add(make_supplier())
        await uow.commit()

    async with InMemoryUnitOfWork(database) as first_read:
        returned = await first_read.suppliers.get_by_id("supplier-1")
        assert returned is not None
        object.__setattr__(returned, "name", "被篡改")

    async with InMemoryUnitOfWork(database) as second_read:
        stored = await second_read.suppliers.get_by_id("supplier-1")

    assert stored is not None
    assert stored.name == "示例供应商"


@pytest.mark.asyncio
async def test_duplicate_business_id_raises_conflict() -> None:
    database = InMemoryDatabase()

    async with InMemoryUnitOfWork(database) as uow:
        await uow.suppliers.add(make_supplier())
        with pytest.raises(ConflictError, match="supplier_id"):
            await uow.suppliers.add(make_supplier())


@pytest.mark.asyncio
async def test_duplicate_order_idempotency_key_raises_conflict() -> None:
    database = InMemoryDatabase()

    async with InMemoryUnitOfWork(database) as uow:
        await uow.orders.add(make_order("order-1", idempotency_key="same-request"))
        with pytest.raises(ConflictError, match="idempotency_key"):
            await uow.orders.add(make_order("order-2", idempotency_key="same-request"))


@pytest.mark.asyncio
async def test_concurrent_order_update_detects_version_conflict() -> None:
    database = InMemoryDatabase()
    async with InMemoryUnitOfWork(database) as setup:
        await setup.orders.add(make_order())
        await setup.commit()

    first = InMemoryUnitOfWork(database)
    second = InMemoryUnitOfWork(database)
    await first.__aenter__()
    await second.__aenter__()
    try:
        first_order = await first.orders.get_by_id("order-1")
        second_order = await second.orders.get_by_id("order-1")
        assert first_order is not None
        assert second_order is not None

        await first.orders.update(
            first_order.transition_to(OrderStatus.PENDING_APPROVAL),
            expected_version=1,
        )
        await second.orders.update(
            second_order.transition_to(OrderStatus.PENDING_APPROVAL),
            expected_version=1,
        )

        await first.commit()
        with pytest.raises(ConflictError, match="version"):
            await second.commit()
    finally:
        await first.__aexit__(None, None, None)
        await second.__aexit__(None, None, None)
