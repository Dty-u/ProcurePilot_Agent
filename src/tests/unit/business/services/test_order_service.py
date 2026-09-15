from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from procurepilot.business.entities import Part, Supplier, SupplierQuotation
from procurepilot.business.enums import Currency, PartStatus, SupplierStatus, Unit
from procurepilot.business.errors import (
    ApprovalRequiredError,
    ConflictError,
    InfrastructureError,
    PermissionDeniedError,
)
from procurepilot.business.in_memory import InMemoryDatabase, InMemoryUnitOfWork
from procurepilot.business.services.order import (
    ActorContext,
    ExecuteOrderRequest,
    OrderService,
    PrepareOrderLine,
    PrepareOrderRequest,
    RepositoryApprovalValidator,
)
from procurepilot.business.value_objects import Money, PositiveQuantity

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def quote(price: str = "12") -> SupplierQuotation:
    return SupplierQuotation(
        quotation_id="quote-1",
        supplier_id="supplier-1",
        part_id="part-1",
        unit_price=Money(Decimal(price), Currency.CNY),
        minimum_order_quantity=PositiveQuantity(Decimal("1"), Unit.PIECE),
        lead_time_days=5,
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=10),
        source="test",
        collected_at=NOW,
    )


async def seed(database: InMemoryDatabase) -> None:
    async with InMemoryUnitOfWork(database) as uow:
        await uow.suppliers.add(
            Supplier("supplier-1", "S-1", "Supplier", SupplierStatus.ACTIVE)
        )
        await uow.parts.add(
            Part("part-1", "P-1", "Part", "spec", Unit.PIECE, PartStatus.ACTIVE)
        )
        await uow.quotations.add(quote())
        await uow.commit()


def prepare_request() -> PrepareOrderRequest:
    return PrepareOrderRequest(
        operation_id="operation-1",
        order_id="order-1",
        order_no="PO-1",
        supplier_id="supplier-1",
        currency=Currency.CNY,
        idempotency_key="idem-1",
        items=(
            PrepareOrderLine(
                order_item_id="item-1",
                part_id="part-1",
                quotation_id="quote-1",
                quantity=PositiveQuantity(Decimal("10"), Unit.PIECE),
            ),
        ),
        requested_at=NOW,
    )


def buyer() -> ActorContext:
    return ActorContext("buyer-1", frozenset({"buyer"}), "trace-1")


def executor() -> ActorContext:
    return ActorContext("approver-1", frozenset({"order_executor"}), "trace-2")


async def prepare(database: InMemoryDatabase):
    service = OrderService(
        lambda: InMemoryUnitOfWork(database),
        approval_validator=RepositoryApprovalValidator(),
    )
    return service, await service.prepare(prepare_request(), buyer())


@pytest.mark.asyncio
async def test_default_approval_validator_denies_execution() -> None:
    database = InMemoryDatabase()
    await seed(database)
    service = OrderService(lambda: InMemoryUnitOfWork(database))
    prepared = await service.prepare(prepare_request(), buyer())

    with pytest.raises(ApprovalRequiredError):
        await service.execute(ExecuteOrderRequest(prepared, "audit-1", NOW), executor())

    assert database.orders == {}


@pytest.mark.asyncio
async def test_same_idempotency_key_returns_single_order() -> None:
    database = InMemoryDatabase()
    await seed(database)
    database.approvals.add(("operation-1", "approver-1"))
    service, prepared = await prepare(database)
    request = ExecuteOrderRequest(prepared, "audit-1", NOW)

    first = await service.execute(request, executor())
    second = await service.execute(request, executor())

    assert second == first
    assert len(database.orders) == 1
    assert len(database.audits) == 1
    assert ("operation-1", "approver-1") not in database.approvals


@pytest.mark.asyncio
async def test_permission_is_checked_for_prepare_and_execute() -> None:
    database = InMemoryDatabase()
    await seed(database)
    service, prepared = await prepare(database)
    nobody = ActorContext("user-1", frozenset(), "trace-3")

    with pytest.raises(PermissionDeniedError):
        await service.prepare(prepare_request(), nobody)
    with pytest.raises(PermissionDeniedError):
        await service.execute(ExecuteOrderRequest(prepared, "audit-1", NOW), nobody)


@pytest.mark.asyncio
async def test_quotation_change_after_prepare_is_rejected() -> None:
    database = InMemoryDatabase()
    await seed(database)
    database.approvals.add(("operation-1", "approver-1"))
    service, prepared = await prepare(database)
    database.quotations["quote-1"] = replace(quote(), unit_price=Money(Decimal("13"), Currency.CNY))

    with pytest.raises(ConflictError, match="quotation changed"):
        await service.execute(ExecuteOrderRequest(prepared, "audit-1", NOW), executor())

    assert database.orders == {}
    assert ("operation-1", "approver-1") in database.approvals


class FailingAudit:
    async def add(self, audit: object) -> None:
        raise InfrastructureError("audit unavailable")

    async def list_for_object(self, object_id: str) -> list[object]:
        return []


class FailingAuditUnitOfWork(InMemoryUnitOfWork):
    async def __aenter__(self):
        uow = await super().__aenter__()
        uow.audits = FailingAudit()  # type: ignore[assignment]
        return uow


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_order_write() -> None:
    database = InMemoryDatabase()
    await seed(database)
    database.approvals.add(("operation-1", "approver-1"))
    _, prepared = await prepare(database)
    service = OrderService(
        lambda: FailingAuditUnitOfWork(database),
        approval_validator=RepositoryApprovalValidator(),
    )

    with pytest.raises(InfrastructureError):
        await service.execute(ExecuteOrderRequest(prepared, "audit-1", NOW), executor())

    assert database.orders == {}
    assert ("operation-1", "approver-1") in database.approvals
