"""Async SQLAlchemy repositories and explicit domain/ORM mappers."""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from procurepilot.business.approval import ApprovalGrant
from procurepilot.business.entities import (
    InventoryItem,
    OperationAudit,
    Part,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierQuotation,
)
from procurepilot.business.enums import (
    Currency,
    OrderAction,
    OrderStatus,
    PartStatus,
    SupplierStatus,
    Unit,
)
from procurepilot.business.errors import ConflictError
from procurepilot.business.order_operations import OrderOperation
from procurepilot.business.query_models import (
    InventorySearchCriteria,
    OrderSearchCriteria,
    PartSearchCriteria,
    QuotationSearchCriteria,
    SupplierSearchCriteria,
)
from procurepilot.business.value_objects import Money, PositiveQuantity, ensure_utc
from procurepilot.infrastructure.orm_models import (
    ApprovalGrantORM,
    IdempotencyRecordORM,
    InventoryItemORM,
    OperationAuditORM,
    OrderOperationORM,
    PartORM,
    PurchaseOrderItemORM,
    PurchaseOrderORM,
    SupplierORM,
    SupplierQuotationORM,
)


def _to_database_time(value: datetime) -> datetime:
    return ensure_utc(value).replace(tzinfo=None)


def _from_database_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def supplier_to_orm(entity: Supplier) -> SupplierORM:
    return SupplierORM(
        supplier_id=entity.supplier_id,
        supplier_code=entity.supplier_code,
        name=entity.name,
        status=entity.status.value,
        quality_score=entity.quality_score,
        delivery_score=entity.delivery_score,
        version=entity.version,
    )


def supplier_from_orm(row: SupplierORM) -> Supplier:
    return Supplier(
        supplier_id=row.supplier_id,
        supplier_code=row.supplier_code,
        name=row.name,
        status=SupplierStatus(row.status),
        quality_score=row.quality_score,
        delivery_score=row.delivery_score,
        version=row.version,
    )


def part_to_orm(entity: Part) -> PartORM:
    return PartORM(
        part_id=entity.part_id,
        part_code=entity.part_code,
        name=entity.name,
        specification=entity.specification,
        unit=entity.unit.value,
        status=entity.status.value,
    )


def part_from_orm(row: PartORM) -> Part:
    return Part(
        part_id=row.part_id,
        part_code=row.part_code,
        name=row.name,
        specification=row.specification,
        unit=Unit(row.unit),
        status=PartStatus(row.status),
    )


def quotation_to_orm(entity: SupplierQuotation) -> SupplierQuotationORM:
    return SupplierQuotationORM(
        quotation_id=entity.quotation_id,
        supplier_id=entity.supplier_id,
        part_id=entity.part_id,
        unit_price=entity.unit_price.amount,
        currency=entity.unit_price.currency.value,
        minimum_order_quantity=entity.minimum_order_quantity.amount,
        unit=entity.minimum_order_quantity.unit.value,
        lead_time_days=entity.lead_time_days,
        valid_from=_to_database_time(entity.valid_from),
        valid_until=_to_database_time(entity.valid_until),
        source=entity.source,
        collected_at=_to_database_time(entity.collected_at),
    )


def quotation_from_orm(row: SupplierQuotationORM) -> SupplierQuotation:
    return SupplierQuotation(
        quotation_id=row.quotation_id,
        supplier_id=row.supplier_id,
        part_id=row.part_id,
        unit_price=Money(row.unit_price, Currency(row.currency)),
        minimum_order_quantity=PositiveQuantity(
            row.minimum_order_quantity,
            Unit(row.unit),
        ),
        lead_time_days=row.lead_time_days,
        valid_from=_from_database_time(row.valid_from),
        valid_until=_from_database_time(row.valid_until),
        source=row.source,
        collected_at=_from_database_time(row.collected_at),
    )


def inventory_to_orm(entity: InventoryItem) -> InventoryItemORM:
    return InventoryItemORM(
        inventory_id=entity.inventory_id,
        part_id=entity.part_id,
        warehouse_code=entity.warehouse_code,
        unit=entity.unit.value,
        on_hand_quantity=entity.on_hand_quantity,
        reserved_quantity=entity.reserved_quantity,
        safety_stock=entity.safety_stock,
        version=entity.version,
    )


def inventory_from_orm(row: InventoryItemORM) -> InventoryItem:
    return InventoryItem(
        inventory_id=row.inventory_id,
        part_id=row.part_id,
        warehouse_code=row.warehouse_code,
        unit=Unit(row.unit),
        on_hand_quantity=row.on_hand_quantity,
        reserved_quantity=row.reserved_quantity,
        safety_stock=row.safety_stock,
        version=row.version,
    )


def purchase_order_item_to_orm(
    entity: PurchaseOrderItem,
    *,
    order_id: str,
) -> PurchaseOrderItemORM:
    return PurchaseOrderItemORM(
        order_item_id=entity.order_item_id,
        order_id=order_id,
        part_id=entity.part_id,
        quantity=entity.quantity.amount,
        unit=entity.quantity.unit.value,
        unit_price=entity.unit_price.amount,
        currency=entity.unit_price.currency.value,
        quotation_id=entity.quotation_id,
    )


def purchase_order_item_from_orm(row: PurchaseOrderItemORM) -> PurchaseOrderItem:
    return PurchaseOrderItem(
        order_item_id=row.order_item_id,
        part_id=row.part_id,
        quantity=PositiveQuantity(row.quantity, Unit(row.unit)),
        unit_price=Money(row.unit_price, Currency(row.currency)),
        quotation_id=row.quotation_id,
    )


def purchase_order_to_orm(entity: PurchaseOrder) -> PurchaseOrderORM:
    row = PurchaseOrderORM(
        order_id=entity.order_id,
        order_no=entity.order_no,
        supplier_id=entity.supplier_id,
        status=entity.status.value,
        currency=entity.currency.value,
        idempotency_key=entity.idempotency_key,
        version=entity.version,
    )
    row.items = [purchase_order_item_to_orm(item, order_id=entity.order_id) for item in entity.items]
    row.idempotency_record = IdempotencyRecordORM(
        idempotency_key=entity.idempotency_key,
        order_id=entity.order_id,
        created_at=_to_database_time(datetime.now(UTC)),
    )
    return row


def purchase_order_from_orm(row: PurchaseOrderORM) -> PurchaseOrder:
    return PurchaseOrder(
        order_id=row.order_id,
        order_no=row.order_no,
        supplier_id=row.supplier_id,
        status=OrderStatus(row.status),
        currency=Currency(row.currency),
        items=tuple(purchase_order_item_from_orm(item) for item in row.items),
        idempotency_key=row.idempotency_key,
        version=row.version,
    )


def audit_to_orm(entity: OperationAudit) -> OperationAuditORM:
    return OperationAuditORM(
        audit_id=entity.audit_id,
        trace_id=entity.trace_id,
        user_id=entity.user_id,
        action=entity.action,
        object_type=entity.object_type,
        object_id=entity.object_id,
        parameter_summary=entity.parameter_summary,
        result=entity.result,
        occurred_at=_to_database_time(entity.occurred_at),
        approved_by=entity.approved_by,
    )


def audit_from_orm(row: OperationAuditORM) -> OperationAudit:
    return OperationAudit(
        audit_id=row.audit_id,
        trace_id=row.trace_id,
        user_id=row.user_id,
        action=row.action,
        object_type=row.object_type,
        object_id=row.object_id,
        parameter_summary=row.parameter_summary,
        result=row.result,
        occurred_at=_from_database_time(row.occurred_at),
        approved_by=row.approved_by,
    )


def operation_to_orm(entity: OrderOperation) -> OrderOperationORM:
    return OrderOperationORM(
        operation_id=entity.operation_id,
        action=entity.action.value,
        status=entity.status,
        actor_id=entity.user_id,
        thread_id=entity.thread_id,
        normalized_payload=entity.normalized_payload,
        parameter_hash=entity.payload_hash,
        created_at=_to_database_time(entity.created_at),
        expires_at=_to_database_time(entity.expires_at),
        completed_at=None,
    )


def operation_from_orm(row: OrderOperationORM) -> OrderOperation:
    return OrderOperation(
        operation_id=row.operation_id,
        action=OrderAction(row.action),
        user_id=row.actor_id,
        thread_id=row.thread_id,
        normalized_payload=row.normalized_payload,
        payload_hash=row.parameter_hash,
        status=cast(Any, row.status),
        created_at=_from_database_time(row.created_at),
        expires_at=_from_database_time(row.expires_at),
    )


def approval_to_orm(entity: ApprovalGrant) -> ApprovalGrantORM:
    return ApprovalGrantORM(
        grant_id=entity.approval_id,
        operation_id=entity.operation_id,
        actor_id=entity.approver_user_id,
        thread_id=entity.thread_id,
        action=entity.action.value,
        decision=entity.decision,
        parameter_hash=entity.payload_hash,
        approved_by=entity.approver_user_id,
        approved_at=_to_database_time(entity.created_at),
        expires_at=_to_database_time(entity.expires_at),
        consumed_at=(
            None if entity.consumed_at is None else _to_database_time(entity.consumed_at)
        ),
    )


def approval_from_orm(row: ApprovalGrantORM) -> ApprovalGrant:
    return ApprovalGrant(
        approval_id=row.grant_id,
        operation_id=row.operation_id,
        approver_user_id=row.actor_id,
        thread_id=row.thread_id,
        action=OrderAction(row.action),
        payload_hash=row.parameter_hash,
        decision=cast(Any, row.decision),
        created_at=_from_database_time(row.approved_at),
        expires_at=_from_database_time(row.expires_at),
        consumed_at=(
            None if row.consumed_at is None else _from_database_time(row.consumed_at)
        ),
    )


class MySQLSupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, supplier_id: str) -> Supplier | None:
        row = await self._session.get(SupplierORM, supplier_id)
        return None if row is None else supplier_from_orm(row)

    async def search(self, criteria: SupplierSearchCriteria) -> list[Supplier]:
        statement = select(SupplierORM)
        if criteria.status is not None:
            statement = statement.where(SupplierORM.status == criteria.status.value)
        if criteria.keyword is not None:
            pattern = f"%{criteria.keyword}%"
            statement = statement.where(
                SupplierORM.name.like(pattern) | SupplierORM.supplier_code.like(pattern)
            )
        rows = await self._session.scalars(statement.limit(criteria.limit))
        return [supplier_from_orm(row) for row in rows]

    async def add(self, supplier: Supplier) -> None:
        self._session.add(supplier_to_orm(supplier))


class MySQLPartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, part_id: str) -> Part | None:
        row = await self._session.get(PartORM, part_id)
        return None if row is None else part_from_orm(row)

    async def search(self, criteria: PartSearchCriteria) -> list[Part]:
        statement = select(PartORM)
        if criteria.status is not None:
            statement = statement.where(PartORM.status == criteria.status.value)
        if criteria.unit is not None:
            statement = statement.where(PartORM.unit == criteria.unit.value)
        if criteria.keyword is not None:
            pattern = f"%{criteria.keyword}%"
            statement = statement.where(
                PartORM.name.like(pattern) | PartORM.part_code.like(pattern)
            )
        rows = await self._session.scalars(statement.limit(criteria.limit))
        return [part_from_orm(row) for row in rows]

    async def add(self, part: Part) -> None:
        self._session.add(part_to_orm(part))


class MySQLQuotationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, quotation_id: str) -> SupplierQuotation | None:
        row = await self._session.get(SupplierQuotationORM, quotation_id)
        return None if row is None else quotation_from_orm(row)

    async def search(self, criteria: QuotationSearchCriteria) -> list[SupplierQuotation]:
        statement = select(SupplierQuotationORM)
        if criteria.part_id is not None:
            statement = statement.where(SupplierQuotationORM.part_id == criteria.part_id)
        if criteria.supplier_id is not None:
            statement = statement.where(SupplierQuotationORM.supplier_id == criteria.supplier_id)
        if criteria.currency is not None:
            statement = statement.where(SupplierQuotationORM.currency == criteria.currency.value)
        if criteria.unit is not None:
            statement = statement.where(SupplierQuotationORM.unit == criteria.unit.value)
        if criteria.quantity is not None:
            statement = statement.where(
                SupplierQuotationORM.unit == criteria.quantity.unit.value,
                SupplierQuotationORM.minimum_order_quantity <= criteria.quantity.amount,
            )
        rows = await self._session.scalars(statement.limit(criteria.limit))
        return [quotation_from_orm(row) for row in rows]

    async def add(self, quotation: SupplierQuotation) -> None:
        self._session.add(quotation_to_orm(quotation))


class MySQLInventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, inventory_id: str) -> InventoryItem | None:
        row = await self._session.get(InventoryItemORM, inventory_id)
        return None if row is None else inventory_from_orm(row)

    async def search(self, criteria: InventorySearchCriteria) -> list[InventoryItem]:
        statement = select(InventoryItemORM)
        if criteria.part_id is not None:
            statement = statement.where(InventoryItemORM.part_id == criteria.part_id)
        if criteria.warehouse_code is not None:
            statement = statement.where(
                InventoryItemORM.warehouse_code == criteria.warehouse_code
            )
        rows = await self._session.scalars(statement.limit(criteria.limit))
        return [inventory_from_orm(row) for row in rows]

    async def add(self, item: InventoryItem) -> None:
        self._session.add(inventory_to_orm(item))


class MySQLOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _order_statement(self) -> Any:
        return select(PurchaseOrderORM).options(selectinload(PurchaseOrderORM.items))

    async def get_by_id(self, order_id: str) -> PurchaseOrder | None:
        row = await self._session.scalar(
            self._order_statement().where(PurchaseOrderORM.order_id == order_id)
        )
        return None if row is None else purchase_order_from_orm(row)

    async def get_by_idempotency_key(self, idempotency_key: str) -> PurchaseOrder | None:
        row = await self._session.scalar(
            self._order_statement().where(
                PurchaseOrderORM.idempotency_key == idempotency_key
            )
        )
        return None if row is None else purchase_order_from_orm(row)

    async def search(self, criteria: OrderSearchCriteria) -> list[PurchaseOrder]:
        statement = self._order_statement()
        if criteria.order_id is not None:
            statement = statement.where(PurchaseOrderORM.order_id == criteria.order_id)
        if criteria.order_no is not None:
            statement = statement.where(PurchaseOrderORM.order_no == criteria.order_no)
        if criteria.supplier_id is not None:
            statement = statement.where(PurchaseOrderORM.supplier_id == criteria.supplier_id)
        if criteria.status is not None:
            statement = statement.where(PurchaseOrderORM.status == criteria.status.value)
        rows = await self._session.scalars(statement.limit(criteria.limit))
        return [purchase_order_from_orm(row) for row in rows.unique()]

    async def add(self, order: PurchaseOrder) -> None:
        self._session.add(purchase_order_to_orm(order))

    async def update(self, order: PurchaseOrder, *, expected_version: int) -> None:
        if order.version != expected_version + 1:
            raise ConflictError(f"order version conflict: {order.order_id}")
        statement = (
            update(PurchaseOrderORM)
            .where(
                PurchaseOrderORM.order_id == order.order_id,
                PurchaseOrderORM.version == expected_version,
            )
            .values(
                order_no=order.order_no,
                supplier_id=order.supplier_id,
                status=order.status.value,
                currency=order.currency.value,
                idempotency_key=order.idempotency_key,
                version=order.version,
            )
        )
        result = cast(CursorResult[Any], await self._session.execute(statement))
        if result.rowcount != 1:
            raise ConflictError(f"order version conflict: {order.order_id}")
        await self._session.execute(
            delete(PurchaseOrderItemORM).where(PurchaseOrderItemORM.order_id == order.order_id)
        )
        await self._session.execute(
            insert(PurchaseOrderItemORM),
            [
                {
                    "order_item_id": item.order_item_id,
                    "order_id": order.order_id,
                    "part_id": item.part_id,
                    "quantity": item.quantity.amount,
                    "unit": item.quantity.unit.value,
                    "unit_price": item.unit_price.amount,
                    "currency": item.unit_price.currency.value,
                    "quotation_id": item.quotation_id,
                }
                for item in order.items
            ],
        )


class MySQLApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, approval_id: str) -> ApprovalGrant | None:
        row = await self._session.get(ApprovalGrantORM, approval_id)
        return None if row is None else approval_from_orm(row)

    async def add(self, approval: ApprovalGrant) -> None:
        self._session.add(approval_to_orm(approval))

    async def update(self, approval: ApprovalGrant) -> None:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(ApprovalGrantORM)
                .where(
                    ApprovalGrantORM.grant_id == approval.approval_id,
                    ApprovalGrantORM.consumed_at.is_(None),
                )
                .values(
                    consumed_at=(
                        None
                        if approval.consumed_at is None
                        else _to_database_time(approval.consumed_at)
                    )
                )
            ),
        )
        if result.rowcount != 1:
            raise ConflictError(f"approval is unavailable: {approval.approval_id}")

    async def is_approved(self, *, operation_id: str, actor_id: str) -> bool:
        grant_id = await self._session.scalar(
            select(ApprovalGrantORM.grant_id).where(
                ApprovalGrantORM.operation_id == operation_id,
                ApprovalGrantORM.actor_id == actor_id,
                ApprovalGrantORM.consumed_at.is_(None),
            )
        )
        return grant_id is not None

    async def consume(self, *, operation_id: str, actor_id: str, at: datetime) -> None:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(ApprovalGrantORM)
                .where(
                    ApprovalGrantORM.operation_id == operation_id,
                    ApprovalGrantORM.actor_id == actor_id,
                    ApprovalGrantORM.consumed_at.is_(None),
                )
                .values(consumed_at=_to_database_time(at))
            ),
        )
        if result.rowcount != 1:
            raise ConflictError(f"approval is unavailable: {operation_id}")


class MySQLOrderOperationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, operation_id: str) -> OrderOperation | None:
        row = await self._session.get(OrderOperationORM, operation_id)
        return None if row is None else operation_from_orm(row)

    async def add(self, operation: OrderOperation) -> None:
        self._session.add(operation_to_orm(operation))

    async def update(self, operation: OrderOperation) -> None:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(OrderOperationORM)
                .where(OrderOperationORM.operation_id == operation.operation_id)
                .values(
                    status=operation.status,
                    completed_at=(
                        _to_database_time(datetime.now(UTC))
                        if operation.status in {"executed", "rejected"}
                        else None
                    ),
                )
            ),
        )
        if result.rowcount != 1:
            raise ConflictError(f"operation is unavailable: {operation.operation_id}")


class MySQLAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, audit: OperationAudit) -> None:
        self._session.add(audit_to_orm(audit))

    async def list_for_object(self, object_id: str) -> list[OperationAudit]:
        rows = await self._session.scalars(
            select(OperationAuditORM).where(OperationAuditORM.object_id == object_id)
        )
        return [audit_from_orm(row) for row in rows]
