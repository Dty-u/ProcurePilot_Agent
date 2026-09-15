import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from procurepilot.business.entities import (
    OperationAudit,
    Part,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
)
from procurepilot.business.enums import Currency, OrderStatus, PartStatus, SupplierStatus, Unit
from procurepilot.business.errors import ConflictError
from procurepilot.business.value_objects import Money, PositiveQuantity
from procurepilot.infrastructure.mysql_uow import MySQLUnitOfWork
from procurepilot.infrastructure.orm_models import (
    ApprovalGrantORM,
    OrderOperationORM,
    PurchaseOrderORM,
)

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def order(order_id: str, idempotency_key: str) -> PurchaseOrder:
    return PurchaseOrder(
        order_id=order_id,
        order_no=f"PO-{order_id}",
        supplier_id="supplier-1",
        status=OrderStatus.DRAFT,
        currency=Currency.CNY,
        items=(
            PurchaseOrderItem(
                f"item-{order_id}",
                "part-1",
                PositiveQuantity(Decimal("1"), Unit.PIECE),
                Money(Decimal("10"), Currency.CNY),
            ),
        ),
        idempotency_key=idempotency_key,
    )


def audit(audit_id: str, object_id: str) -> OperationAudit:
    return OperationAudit(
        audit_id,
        "trace-1",
        "user-1",
        "create_order",
        "purchase_order",
        object_id,
        "safe summary",
        "created",
        NOW,
    )


async def seed_catalog(factory: async_sessionmaker[AsyncSession]) -> None:
    async with MySQLUnitOfWork(factory) as uow:
        await uow.suppliers.add(
            Supplier("supplier-1", "S-1", "Supplier", SupplierStatus.ACTIVE)
        )
        await uow.parts.add(
            Part("part-1", "P-1", "Part", "spec", Unit.PIECE, PartStatus.ACTIVE)
        )
        await uow.commit()


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_order(
    mysql_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_catalog(mysql_session_factory)
    async with MySQLUnitOfWork(mysql_session_factory) as uow:
        await uow.audits.add(audit("audit-1", "existing"))
        await uow.commit()

    async with MySQLUnitOfWork(mysql_session_factory) as uow:
        await uow.orders.add(order("order-1", "idem-1"))
        await uow.audits.add(audit("audit-1", "order-1"))
        with pytest.raises(ConflictError):
            await uow.commit()

    async with MySQLUnitOfWork(mysql_session_factory) as uow:
        assert await uow.orders.get_by_id("order-1") is None


@pytest.mark.asyncio
async def test_optimistic_update_allows_only_one_version(
    mysql_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_catalog(mysql_session_factory)
    async with MySQLUnitOfWork(mysql_session_factory) as seed_uow:
        await seed_uow.orders.add(order("order-1", "idem-1"))
        await seed_uow.commit()

    first = MySQLUnitOfWork(mysql_session_factory)
    second = MySQLUnitOfWork(mysql_session_factory)
    await first.__aenter__()
    await second.__aenter__()
    try:
        first_order = await first.orders.get_by_id("order-1")
        second_order = await second.orders.get_by_id("order-1")
        assert first_order is not None and second_order is not None
        await first.orders.update(replace(first_order, status=OrderStatus.PENDING_APPROVAL, version=2), expected_version=1)
        await first.commit()

        with pytest.raises(ConflictError, match="version conflict"):
            await second.orders.update(
                replace(second_order, status=OrderStatus.PENDING_APPROVAL, version=2),
                expected_version=1,
            )
    finally:
        await first.__aexit__(None, None, None)
        await second.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_concurrent_idempotency_key_creates_one_order(
    mysql_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_catalog(mysql_session_factory)

    async def create(candidate: PurchaseOrder) -> str:
        try:
            async with MySQLUnitOfWork(mysql_session_factory) as uow:
                await uow.orders.add(candidate)
                await uow.commit()
            return "created"
        except ConflictError:
            return "conflict"

    outcomes = await asyncio.gather(
        create(order("order-1", "same-key")),
        create(order("order-2", "same-key")),
    )

    async with mysql_session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(PurchaseOrderORM))
    assert sorted(outcomes) == ["conflict", "created"]
    assert count == 1


@pytest.mark.asyncio
async def test_failed_transaction_does_not_consume_approval(
    mysql_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_catalog(mysql_session_factory)
    async with mysql_session_factory() as session:
        session.add(
            OrderOperationORM(
                operation_id="operation-1",
                action="create",
                status="approved",
                actor_id="executor-1",
                parameter_hash="hash",
                created_at=NOW.replace(tzinfo=None),
            )
        )
        session.add(
            ApprovalGrantORM(
                grant_id="grant-1",
                operation_id="operation-1",
                actor_id="executor-1",
                parameter_hash="hash",
                approved_by="approver-1",
                approved_at=NOW.replace(tzinfo=None),
            )
        )
        await session.commit()
    async with MySQLUnitOfWork(mysql_session_factory) as uow:
        await uow.audits.add(audit("audit-1", "existing"))
        await uow.commit()

    async with MySQLUnitOfWork(mysql_session_factory) as uow:
        await uow.approvals.consume(operation_id="operation-1", actor_id="executor-1", at=NOW)
        await uow.orders.add(order("order-1", "idem-1"))
        await uow.audits.add(audit("audit-1", "order-1"))
        with pytest.raises(ConflictError):
            await uow.commit()

    async with mysql_session_factory() as session:
        consumed_at = await session.scalar(
            select(ApprovalGrantORM.consumed_at).where(ApprovalGrantORM.grant_id == "grant-1")
        )
    assert consumed_at is None
