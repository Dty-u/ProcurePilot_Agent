"""Purchase order preparation and atomic execution services."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from procurepilot.business.approval import ApprovalGrant
from procurepilot.business.entities import (
    OperationAudit,
    PurchaseOrder,
    PurchaseOrderItem,
    SupplierQuotation,
)
from procurepilot.business.enums import Currency, OrderStatus, Unit
from procurepilot.business.errors import (
    ApprovalRequiredError,
    ConflictError,
    EntityNotFoundError,
    PermissionDeniedError,
)
from procurepilot.business.order_operations import (
    CancelOrderPayload,
    CreateOrderPayload,
    OrderLinePayload,
    OrderOperation,
    UpdateOrderPayload,
    compute_payload_hash,
)
from procurepilot.business.repositories import UnitOfWork
from procurepilot.business.value_objects import PositiveQuantity, ensure_utc


@dataclass(frozen=True, slots=True)
class ActorContext:
    actor_id: str
    roles: frozenset[str]
    trace_id: str
    thread_id: str | None = None


@dataclass(frozen=True, slots=True)
class PrepareOrderLine:
    order_item_id: str
    part_id: str
    quotation_id: str
    quantity: PositiveQuantity


@dataclass(frozen=True, slots=True)
class PrepareOrderRequest:
    operation_id: str
    order_id: str
    order_no: str
    supplier_id: str
    currency: Currency
    idempotency_key: str
    items: tuple[PrepareOrderLine, ...]
    requested_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "requested_at", ensure_utc(self.requested_at))


@dataclass(frozen=True, slots=True)
class PreparedOrder:
    operation_id: str
    order: PurchaseOrder
    quotation_snapshots: tuple[SupplierQuotation, ...]
    requested_at: datetime


@dataclass(frozen=True, slots=True)
class ExecuteOrderRequest:
    prepared: PreparedOrder
    audit_id: str
    executed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "executed_at", ensure_utc(self.executed_at))


@dataclass(frozen=True, slots=True)
class ExecuteSavedOperationRequest:
    operation_id: str
    approval_id: str
    idempotency_key: str
    audit_id: str
    executed_at: datetime
    expected_version: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "executed_at", ensure_utc(self.executed_at))


class ApprovalValidator(Protocol):
    async def ensure_approved(
        self,
        *,
        uow: UnitOfWork,
        operation_id: str,
        context: ActorContext,
        at: datetime,
    ) -> None: ...


class DenyAllApprovalValidator:
    async def ensure_approved(
        self,
        *,
        uow: UnitOfWork,
        operation_id: str,
        context: ActorContext,
        at: datetime,
    ) -> None:
        raise ApprovalRequiredError(f"operation requires approval: {operation_id}")


class RepositoryApprovalValidator:
    async def ensure_approved(
        self,
        *,
        uow: UnitOfWork,
        operation_id: str,
        context: ActorContext,
        at: datetime,
    ) -> None:
        approved = await uow.approvals.is_approved(
            operation_id=operation_id,
            actor_id=context.actor_id,
        )
        if not approved:
            raise ApprovalRequiredError(f"operation requires approval: {operation_id}")
        await uow.approvals.consume(
            operation_id=operation_id,
            actor_id=context.actor_id,
            at=at,
        )


class OrderService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        *,
        approval_validator: ApprovalValidator | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._approval_validator = approval_validator or DenyAllApprovalValidator()

    async def record_approval(self, approval: ApprovalGrant) -> None:
        """Persist a trusted UI/API decision; this method is never exposed as an Agent tool."""

        async with self._uow_factory() as uow:
            operation = await uow.operations.get_by_id(approval.operation_id)
            if operation is None:
                raise EntityNotFoundError(f"operation not found: {approval.operation_id}")
            if operation.status != "pending_approval":
                raise ConflictError(f"operation cannot be decided: {operation.status}")
            if (
                approval.approver_user_id != operation.user_id
                or approval.thread_id != operation.thread_id
            ):
                raise PermissionDeniedError("approval identity scope mismatch")
            if approval.action is not operation.action or approval.payload_hash != operation.payload_hash:
                raise ConflictError("approval does not match the saved operation")
            await uow.approvals.add(approval)
            await uow.operations.update(
                operation.with_status(
                    "approved" if approval.decision == "approve" else "rejected"
                )
            )
            await uow.commit()

    async def prepare(
        self,
        request: PrepareOrderRequest,
        context: ActorContext,
    ) -> PreparedOrder:
        self._require_role(context, "buyer")
        async with self._uow_factory() as uow:
            supplier = await uow.suppliers.get_by_id(request.supplier_id)
            if supplier is None:
                raise EntityNotFoundError(f"supplier not found: {request.supplier_id}")
            supplier.ensure_procurement_eligible()

            order_items: list[PurchaseOrderItem] = []
            snapshots: list[SupplierQuotation] = []
            for line in request.items:
                part = await uow.parts.get_by_id(line.part_id)
                if part is None:
                    raise EntityNotFoundError(f"part not found: {line.part_id}")
                part.ensure_procurement_eligible()
                quotation = await uow.quotations.get_by_id(line.quotation_id)
                self._validate_quotation(quotation, request, line, part.unit)
                assert quotation is not None
                order_items.append(
                    PurchaseOrderItem(
                        order_item_id=line.order_item_id,
                        part_id=line.part_id,
                        quantity=line.quantity,
                        unit_price=quotation.unit_price,
                        quotation_id=quotation.quotation_id,
                    )
                )
                snapshots.append(quotation)

        order = PurchaseOrder(
            order_id=request.order_id,
            order_no=request.order_no,
            supplier_id=request.supplier_id,
            status=OrderStatus.DRAFT,
            currency=request.currency,
            items=tuple(order_items),
            idempotency_key=request.idempotency_key,
        )
        return PreparedOrder(
            operation_id=request.operation_id,
            order=order,
            quotation_snapshots=tuple(snapshots),
            requested_at=request.requested_at,
        )

    async def execute(
        self,
        request: ExecuteOrderRequest,
        context: ActorContext,
    ) -> PurchaseOrder:
        self._require_role(context, "order_executor")
        prepared = request.prepared
        async with self._uow_factory() as uow:
            existing = await uow.orders.get_by_idempotency_key(
                prepared.order.idempotency_key
            )
            if existing is not None:
                if existing.order_id != prepared.order.order_id:
                    raise ConflictError("idempotency key belongs to a different order")
                return existing

            await self._approval_validator.ensure_approved(
                uow=uow,
                operation_id=prepared.operation_id,
                context=context,
                at=request.executed_at,
            )
            await self._ensure_quotations_unchanged(uow, prepared, request.executed_at)

            order = (
                prepared.order.transition_to(OrderStatus.PENDING_APPROVAL)
                .transition_to(OrderStatus.APPROVED)
                .transition_to(OrderStatus.CREATED)
            )
            await uow.orders.add(order)
            await uow.audits.add(
                OperationAudit(
                    audit_id=request.audit_id,
                    trace_id=context.trace_id,
                    user_id=context.actor_id,
                    action="create_order",
                    object_type="purchase_order",
                    object_id=order.order_id,
                    parameter_summary=(
                        f"operation_id={prepared.operation_id}; "
                        f"idempotency_key={order.idempotency_key}; items={len(order.items)}"
                    ),
                    result="created",
                    occurred_at=request.executed_at,
                    approved_by=context.actor_id,
                )
            )
            await uow.commit()
            return order

    async def execute_saved(
        self,
        request: ExecuteSavedOperationRequest,
        context: ActorContext,
    ) -> PurchaseOrder:
        """Execute only the immutable operation snapshot bound to a trusted approval."""

        self._require_role(context, "order_executor")
        if context.thread_id is None:
            raise PermissionDeniedError("trusted thread context is required")

        async with self._uow_factory() as uow:
            operation = await uow.operations.get_by_id(request.operation_id)
            if operation is None:
                raise EntityNotFoundError(f"operation not found: {request.operation_id}")
            self._validate_operation_binding(operation, context)
            payload = operation.parse_payload()
            if isinstance(payload, CreateOrderPayload):
                existing = await uow.orders.get_by_idempotency_key(request.idempotency_key)
                if existing is not None:
                    if existing.order_id != payload.order_id:
                        raise ConflictError("idempotency key belongs to a different order")
                    return existing

            self._validate_saved_operation(operation, request.executed_at)

            approval = await uow.approvals.get_by_id(request.approval_id)
            if approval is None:
                raise ApprovalRequiredError(f"approval not found: {request.approval_id}")
            consumed = approval.authorize_and_consume(
                operation_id=operation.operation_id,
                user_id=context.actor_id,
                thread_id=context.thread_id,
                action=operation.action,
                payload_hash=operation.payload_hash,
                at=request.executed_at,
            )

            order = await self._apply_saved_payload(
                uow=uow,
                payload=payload,
                request=request,
            )
            await uow.approvals.update(consumed)
            await uow.operations.update(operation.with_status("executed"))
            await uow.audits.add(
                OperationAudit(
                    audit_id=request.audit_id,
                    trace_id=context.trace_id,
                    user_id=context.actor_id,
                    action=f"{operation.action.value}_order",
                    object_type="purchase_order",
                    object_id=order.order_id,
                    parameter_summary=(
                        f"operation_id={operation.operation_id}; "
                        f"payload_hash={operation.payload_hash}; version={order.version}"
                    ),
                    result=operation.action.value,
                    occurred_at=request.executed_at,
                    approved_by=approval.approver_user_id,
                )
            )
            await uow.commit()
            return order

    @staticmethod
    def _validate_saved_operation(
        operation: OrderOperation,
        executed_at: datetime,
    ) -> None:
        if operation.status == "rejected":
            raise ApprovalRequiredError("order operation was rejected")
        if operation.status not in {"pending_approval", "approved"}:
            raise ConflictError(f"order operation is not executable: {operation.status}")
        if executed_at >= operation.expires_at:
            raise ApprovalRequiredError("order operation expired")

    @staticmethod
    def _validate_operation_binding(
        operation: OrderOperation,
        context: ActorContext,
    ) -> None:
        if operation.user_id != context.actor_id or operation.thread_id != context.thread_id:
            raise PermissionDeniedError("order operation identity scope mismatch")
        if compute_payload_hash(operation.parse_payload()) != operation.payload_hash:
            raise ConflictError("saved operation payload was changed after preparation")

    async def _apply_saved_payload(
        self,
        *,
        uow: UnitOfWork,
        payload: CreateOrderPayload | UpdateOrderPayload | CancelOrderPayload,
        request: ExecuteSavedOperationRequest,
    ) -> PurchaseOrder:
        if isinstance(payload, CreateOrderPayload):
            order = await self._create_from_payload(uow, payload, request)
            await uow.orders.add(order)
            return order

        existing_order = await uow.orders.get_by_id(payload.target_order_id)
        if existing_order is None:
            raise EntityNotFoundError(f"order not found: {payload.target_order_id}")
        if request.expected_version != payload.expected_version:
            raise ConflictError("expected_version does not match the saved operation")
        if existing_order.version != payload.expected_version:
            raise ConflictError(f"order version conflict: {existing_order.order_id}")

        if isinstance(payload, UpdateOrderPayload):
            items = await self._items_from_lines(
                uow,
                supplier_id=existing_order.supplier_id,
                currency=existing_order.currency,
                lines=payload.items,
                valid_at=request.executed_at,
            )
            updated = existing_order.replace_items(tuple(items))
        else:
            updated = existing_order.transition_to(OrderStatus.CANCELLED)
        await uow.orders.update(updated, expected_version=payload.expected_version)
        return updated

    async def _create_from_payload(
        self,
        uow: UnitOfWork,
        payload: CreateOrderPayload,
        request: ExecuteSavedOperationRequest,
    ) -> PurchaseOrder:
        supplier = await uow.suppliers.get_by_id(payload.supplier_id)
        if supplier is None:
            raise EntityNotFoundError(f"supplier not found: {payload.supplier_id}")
        supplier.ensure_procurement_eligible()
        items = await self._items_from_lines(
            uow,
            supplier_id=payload.supplier_id,
            currency=payload.currency,
            lines=payload.items,
            valid_at=request.executed_at,
        )
        return PurchaseOrder(
            order_id=payload.order_id,
            order_no=payload.order_no,
            supplier_id=payload.supplier_id,
            status=OrderStatus.CREATED,
            currency=payload.currency,
            items=tuple(items),
            idempotency_key=request.idempotency_key,
        )

    async def _items_from_lines(
        self,
        uow: UnitOfWork,
        *,
        supplier_id: str,
        currency: Currency,
        lines: tuple[OrderLinePayload, ...],
        valid_at: datetime,
    ) -> list[PurchaseOrderItem]:
        items: list[PurchaseOrderItem] = []
        for line in lines:
            part = await uow.parts.get_by_id(line.part_id)
            if part is None:
                raise EntityNotFoundError(f"part not found: {line.part_id}")
            part.ensure_procurement_eligible()
            if line.unit is not part.unit:
                raise ConflictError("order line unit does not match the saved part")
            quotation = await uow.quotations.get_by_id(line.quotation_id)
            quantity = PositiveQuantity(line.quantity, line.unit)
            if quotation is None:
                raise EntityNotFoundError(f"quotation not found: {line.quotation_id}")
            if quotation.supplier_id != supplier_id or quotation.part_id != line.part_id:
                raise ConflictError("quotation does not match the saved supplier and part")
            if quotation.unit_price.currency is not currency:
                raise ConflictError("quotation currency mismatch")
            if not quotation.is_valid_at(valid_at) or not quotation.supports_quantity(quantity):
                raise ConflictError(f"quotation is not valid: {quotation.quotation_id}")
            items.append(
                PurchaseOrderItem(
                    order_item_id=line.order_item_id,
                    part_id=line.part_id,
                    quantity=quantity,
                    unit_price=quotation.unit_price,
                    quotation_id=quotation.quotation_id,
                )
            )
        return items

    @staticmethod
    def _require_role(context: ActorContext, role: str) -> None:
        if role not in context.roles:
            raise PermissionDeniedError(f"role required: {role}")

    @staticmethod
    def _validate_quotation(
        quotation: SupplierQuotation | None,
        request: PrepareOrderRequest,
        line: PrepareOrderLine,
        part_unit: Unit,
    ) -> None:
        if quotation is None:
            raise EntityNotFoundError(f"quotation not found: {line.quotation_id}")
        if quotation.supplier_id != request.supplier_id or quotation.part_id != line.part_id:
            raise ConflictError("quotation does not match the requested supplier and part")
        if not quotation.is_valid_at(request.requested_at):
            raise ConflictError(f"quotation is not valid: {quotation.quotation_id}")
        if quotation.unit_price.currency is not request.currency:
            raise ConflictError("quotation currency mismatch")
        if quotation.minimum_order_quantity.unit is not part_unit:
            raise ConflictError("quotation unit mismatch")
        if not quotation.supports_quantity(line.quantity):
            raise ConflictError("minimum order quantity is not met")

    @staticmethod
    async def _ensure_quotations_unchanged(
        uow: UnitOfWork,
        prepared: PreparedOrder,
        executed_at: datetime,
    ) -> None:
        for snapshot in prepared.quotation_snapshots:
            current = await uow.quotations.get_by_id(snapshot.quotation_id)
            if current != snapshot or current is None or not current.is_valid_at(executed_at):
                raise ConflictError(f"quotation changed: {snapshot.quotation_id}")
