from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from procurepilot.business.approval import ApprovalGrant
from procurepilot.business.entities import Part, Supplier, SupplierQuotation
from procurepilot.business.enums import Currency, OrderAction, PartStatus, SupplierStatus, Unit
from procurepilot.business.order_operations import (
    CreateOrderPayload,
    OrderLinePayload,
    OrderOperation,
)
from procurepilot.business.repositories import UnitOfWork
from procurepilot.business.services.order import (
    ActorContext,
    ExecuteSavedOperationRequest,
    OrderService,
)
from procurepilot.business.value_objects import Money, PositiveQuantity
from procurepilot.infrastructure.mysql_uow import MySQLUnitOfWork

NOW = datetime(2026, 9, 9, tzinfo=UTC)


@pytest.mark.asyncio
async def test_mysql_approval_consumption_order_and_audit_commit_atomically(
    mysql_session_factory,
) -> None:
    def uow_factory() -> UnitOfWork:
        return cast(UnitOfWork, MySQLUnitOfWork(mysql_session_factory))

    operation = OrderOperation.create(
        operation_id="operation-hitl-1",
        action=OrderAction.CREATE,
        user_id="user-1",
        thread_id="thread-1",
        payload=CreateOrderPayload(
            order_id="order-hitl-1",
            order_no="PO-HITL-1",
            supplier_id="supplier-hitl-1",
            currency=Currency.CNY,
            requested_at=NOW,
            items=(
                OrderLinePayload(
                    order_item_id="item-hitl-1",
                    part_id="part-hitl-1",
                    quotation_id="quote-hitl-1",
                    quantity=Decimal("10"),
                    unit=Unit.PIECE,
                ),
            ),
        ),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    async with uow_factory() as uow:
        await uow.suppliers.add(
            Supplier("supplier-hitl-1", "S-HITL-1", "Supplier", SupplierStatus.ACTIVE)
        )
        await uow.parts.add(
            Part(
                "part-hitl-1",
                "P-HITL-1",
                "Part",
                "spec",
                Unit.PIECE,
                PartStatus.ACTIVE,
            )
        )
        await uow.quotations.add(
            SupplierQuotation(
                quotation_id="quote-hitl-1",
                supplier_id="supplier-hitl-1",
                part_id="part-hitl-1",
                unit_price=Money(Decimal("12"), Currency.CNY),
                minimum_order_quantity=PositiveQuantity(Decimal("1"), Unit.PIECE),
                lead_time_days=2,
                valid_from=NOW - timedelta(days=1),
                valid_until=NOW + timedelta(days=1),
                source="integration",
                collected_at=NOW,
            )
        )
        await uow.operations.add(operation)
        await uow.commit()

    service = OrderService(uow_factory)
    await service.record_approval(
        ApprovalGrant(
            approval_id="approval-hitl-1",
            operation_id=operation.operation_id,
            approver_user_id=operation.user_id,
            thread_id=operation.thread_id,
            action=operation.action,
            payload_hash=operation.payload_hash,
            decision="approve",
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )
    )
    order = await service.execute_saved(
        ExecuteSavedOperationRequest(
            operation_id=operation.operation_id,
            approval_id="approval-hitl-1",
            idempotency_key="idem-hitl-1",
            audit_id="audit-hitl-1",
            executed_at=NOW + timedelta(seconds=1),
        ),
        ActorContext(
            "user-1",
            frozenset({"order_executor"}),
            "trace-hitl-1",
            "thread-1",
        ),
    )

    async with uow_factory() as uow:
        approval = await uow.approvals.get_by_id("approval-hitl-1")
        audits = await uow.audits.list_for_object(order.order_id)
        saved_operation = await uow.operations.get_by_id(operation.operation_id)

    assert approval is not None and approval.consumed_at is not None
    assert len(audits) == 1
    assert saved_operation is not None and saved_operation.status == "executed"
