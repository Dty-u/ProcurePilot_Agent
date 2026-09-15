"""In-memory repository implementations with optimistic transaction semantics."""

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

from procurepilot.business.approval import ApprovalGrant
from procurepilot.business.entities import (
    InventoryItem,
    OperationAudit,
    Part,
    PurchaseOrder,
    Supplier,
    SupplierQuotation,
)
from procurepilot.business.errors import ConflictError, EntityNotFoundError
from procurepilot.business.order_operations import OrderOperation
from procurepilot.business.query_models import (
    InventorySearchCriteria,
    OrderSearchCriteria,
    PartSearchCriteria,
    QuotationSearchCriteria,
    SupplierSearchCriteria,
)


@dataclass(slots=True)
class InMemoryDatabase:
    suppliers: dict[str, Supplier] = field(default_factory=dict)
    parts: dict[str, Part] = field(default_factory=dict)
    quotations: dict[str, SupplierQuotation] = field(default_factory=dict)
    inventory: dict[str, InventoryItem] = field(default_factory=dict)
    orders: dict[str, PurchaseOrder] = field(default_factory=dict)
    approvals: set[tuple[str, str]] = field(default_factory=set)
    approval_grants: dict[str, ApprovalGrant] = field(default_factory=dict)
    order_operations: dict[str, OrderOperation] = field(default_factory=dict)
    audits: dict[str, OperationAudit] = field(default_factory=dict)

    def clone(self) -> "InMemoryDatabase":
        return deepcopy(self)

    def replace_with(self, other: "InMemoryDatabase") -> None:
        self.suppliers = deepcopy(other.suppliers)
        self.parts = deepcopy(other.parts)
        self.quotations = deepcopy(other.quotations)
        self.inventory = deepcopy(other.inventory)
        self.orders = deepcopy(other.orders)
        self.approvals = deepcopy(other.approvals)
        self.approval_grants = deepcopy(other.approval_grants)
        self.order_operations = deepcopy(other.order_operations)
        self.audits = deepcopy(other.audits)


class InMemorySupplierRepository:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._database = database

    async def get_by_id(self, supplier_id: str) -> Supplier | None:
        return deepcopy(self._database.suppliers.get(supplier_id))

    async def search(self, criteria: SupplierSearchCriteria) -> list[Supplier]:
        suppliers: Iterable[Supplier] = self._database.suppliers.values()
        if criteria.status is not None:
            suppliers = (supplier for supplier in suppliers if supplier.status is criteria.status)
        if criteria.keyword is not None:
            keyword = criteria.keyword.casefold()
            suppliers = (
                supplier
                for supplier in suppliers
                if keyword in supplier.name.casefold()
                or keyword in supplier.supplier_code.casefold()
            )
        return deepcopy(list(suppliers)[: criteria.limit])

    async def add(self, supplier: Supplier) -> None:
        if supplier.supplier_id in self._database.suppliers:
            raise ConflictError(f"supplier_id already exists: {supplier.supplier_id}")
        if any(
            existing.supplier_code == supplier.supplier_code
            for existing in self._database.suppliers.values()
        ):
            raise ConflictError(f"supplier_code already exists: {supplier.supplier_code}")
        self._database.suppliers[supplier.supplier_id] = deepcopy(supplier)


class InMemoryPartRepository:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._database = database

    async def get_by_id(self, part_id: str) -> Part | None:
        return deepcopy(self._database.parts.get(part_id))

    async def search(self, criteria: PartSearchCriteria) -> list[Part]:
        parts: Iterable[Part] = self._database.parts.values()
        if criteria.status is not None:
            parts = (part for part in parts if part.status is criteria.status)
        if criteria.unit is not None:
            parts = (part for part in parts if part.unit is criteria.unit)
        if criteria.keyword is not None:
            keyword = criteria.keyword.casefold()
            parts = (
                part
                for part in parts
                if keyword in part.name.casefold() or keyword in part.part_code.casefold()
            )
        return deepcopy(list(parts)[: criteria.limit])

    async def add(self, part: Part) -> None:
        if part.part_id in self._database.parts:
            raise ConflictError(f"part_id already exists: {part.part_id}")
        if any(
            existing.part_code == part.part_code for existing in self._database.parts.values()
        ):
            raise ConflictError(f"part_code already exists: {part.part_code}")
        self._database.parts[part.part_id] = deepcopy(part)


class InMemoryQuotationRepository:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._database = database

    async def get_by_id(self, quotation_id: str) -> SupplierQuotation | None:
        return deepcopy(self._database.quotations.get(quotation_id))

    async def search(self, criteria: QuotationSearchCriteria) -> list[SupplierQuotation]:
        quotations: Iterable[SupplierQuotation] = self._database.quotations.values()
        if criteria.part_id is not None:
            quotations = (
                quotation for quotation in quotations if quotation.part_id == criteria.part_id
            )
        if criteria.supplier_id is not None:
            quotations = (
                quotation
                for quotation in quotations
                if quotation.supplier_id == criteria.supplier_id
            )
        if criteria.currency is not None:
            quotations = (
                quotation
                for quotation in quotations
                if quotation.unit_price.currency is criteria.currency
            )
        if criteria.unit is not None:
            quotations = (
                quotation
                for quotation in quotations
                if quotation.minimum_order_quantity.unit is criteria.unit
            )
        if criteria.quantity is not None:
            quotations = (
                quotation
                for quotation in quotations
                if quotation.supports_quantity(criteria.quantity)
            )
        return deepcopy(list(quotations)[: criteria.limit])

    async def add(self, quotation: SupplierQuotation) -> None:
        if quotation.quotation_id in self._database.quotations:
            raise ConflictError(f"quotation_id already exists: {quotation.quotation_id}")
        self._database.quotations[quotation.quotation_id] = deepcopy(quotation)


class InMemoryInventoryRepository:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._database = database

    async def get_by_id(self, inventory_id: str) -> InventoryItem | None:
        return deepcopy(self._database.inventory.get(inventory_id))

    async def search(self, criteria: InventorySearchCriteria) -> list[InventoryItem]:
        inventory: Iterable[InventoryItem] = self._database.inventory.values()
        if criteria.part_id is not None:
            inventory = (item for item in inventory if item.part_id == criteria.part_id)
        if criteria.warehouse_code is not None:
            inventory = (
                item for item in inventory if item.warehouse_code == criteria.warehouse_code
            )
        return deepcopy(list(inventory)[: criteria.limit])

    async def add(self, item: InventoryItem) -> None:
        if item.inventory_id in self._database.inventory:
            raise ConflictError(f"inventory_id already exists: {item.inventory_id}")
        self._database.inventory[item.inventory_id] = deepcopy(item)


class InMemoryOrderRepository:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._database = database

    async def get_by_id(self, order_id: str) -> PurchaseOrder | None:
        return deepcopy(self._database.orders.get(order_id))

    async def get_by_idempotency_key(self, idempotency_key: str) -> PurchaseOrder | None:
        for order in self._database.orders.values():
            if order.idempotency_key == idempotency_key:
                return deepcopy(order)
        return None

    async def search(self, criteria: OrderSearchCriteria) -> list[PurchaseOrder]:
        orders: Iterable[PurchaseOrder] = self._database.orders.values()
        if criteria.order_id is not None:
            orders = (order for order in orders if order.order_id == criteria.order_id)
        if criteria.order_no is not None:
            orders = (order for order in orders if order.order_no == criteria.order_no)
        if criteria.supplier_id is not None:
            orders = (order for order in orders if order.supplier_id == criteria.supplier_id)
        if criteria.status is not None:
            orders = (order for order in orders if order.status is criteria.status)
        return deepcopy(list(orders)[: criteria.limit])

    async def add(self, order: PurchaseOrder) -> None:
        if order.order_id in self._database.orders:
            raise ConflictError(f"order_id already exists: {order.order_id}")
        if any(
            existing.idempotency_key == order.idempotency_key
            for existing in self._database.orders.values()
        ):
            raise ConflictError(f"idempotency_key already exists: {order.idempotency_key}")
        self._database.orders[order.order_id] = deepcopy(order)

    async def update(self, order: PurchaseOrder, *, expected_version: int) -> None:
        current = self._database.orders.get(order.order_id)
        if current is None:
            raise EntityNotFoundError(f"order not found: {order.order_id}")
        if current.version != expected_version or order.version != expected_version + 1:
            raise ConflictError(f"order version conflict: {order.order_id}")
        self._database.orders[order.order_id] = deepcopy(order)


class InMemoryApprovalRepository:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._database = database

    async def get_by_id(self, approval_id: str) -> ApprovalGrant | None:
        return deepcopy(self._database.approval_grants.get(approval_id))

    async def add(self, approval: ApprovalGrant) -> None:
        if approval.approval_id in self._database.approval_grants:
            raise ConflictError(f"approval_id already exists: {approval.approval_id}")
        self._database.approval_grants[approval.approval_id] = deepcopy(approval)

    async def update(self, approval: ApprovalGrant) -> None:
        if approval.approval_id not in self._database.approval_grants:
            raise EntityNotFoundError(f"approval not found: {approval.approval_id}")
        self._database.approval_grants[approval.approval_id] = deepcopy(approval)

    async def is_approved(self, *, operation_id: str, actor_id: str) -> bool:
        return (operation_id, actor_id) in self._database.approvals

    async def consume(self, *, operation_id: str, actor_id: str, at: datetime) -> None:
        approval = (operation_id, actor_id)
        if approval not in self._database.approvals:
            raise ConflictError(f"approval is unavailable: {operation_id}")
        self._database.approvals.remove(approval)


class InMemoryOrderOperationRepository:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._database = database

    async def get_by_id(self, operation_id: str) -> OrderOperation | None:
        return deepcopy(self._database.order_operations.get(operation_id))

    async def add(self, operation: OrderOperation) -> None:
        if operation.operation_id in self._database.order_operations:
            raise ConflictError(f"operation_id already exists: {operation.operation_id}")
        self._database.order_operations[operation.operation_id] = deepcopy(operation)

    async def update(self, operation: OrderOperation) -> None:
        if operation.operation_id not in self._database.order_operations:
            raise EntityNotFoundError(f"operation not found: {operation.operation_id}")
        self._database.order_operations[operation.operation_id] = deepcopy(operation)


class InMemoryAuditRepository:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._database = database

    async def add(self, audit: OperationAudit) -> None:
        if audit.audit_id in self._database.audits:
            raise ConflictError(f"audit_id already exists: {audit.audit_id}")
        self._database.audits[audit.audit_id] = deepcopy(audit)

    async def list_for_object(self, object_id: str) -> list[OperationAudit]:
        return deepcopy(
            [audit for audit in self._database.audits.values() if audit.object_id == object_id]
        )


class InMemoryUnitOfWork:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._shared = database
        self._base: InMemoryDatabase | None = None
        self._working: InMemoryDatabase | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        self._base = self._shared.clone()
        self._working = self._base.clone()
        self.suppliers = InMemorySupplierRepository(self._working)
        self.parts = InMemoryPartRepository(self._working)
        self.quotations = InMemoryQuotationRepository(self._working)
        self.inventory = InMemoryInventoryRepository(self._working)
        self.orders = InMemoryOrderRepository(self._working)
        self.approvals = InMemoryApprovalRepository(self._working)
        self.operations = InMemoryOrderOperationRepository(self._working)
        self.audits = InMemoryAuditRepository(self._working)
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None or not self._committed:
            await self.rollback()

    async def commit(self) -> None:
        base = self._require_database(self._base)
        working = self._require_database(self._working)
        self._ensure_no_concurrent_changes(base)
        self._shared.replace_with(working)
        self._committed = True

    async def rollback(self) -> None:
        self._working = None
        self._committed = False

    def _ensure_no_concurrent_changes(self, base: InMemoryDatabase) -> None:
        for order_id, base_order in base.orders.items():
            shared_order = self._shared.orders.get(order_id)
            if shared_order is not None and shared_order.version != base_order.version:
                raise ConflictError(f"order version conflict: {order_id}")
        if self._shared != base:
            raise ConflictError("concurrent transaction conflict")

    @staticmethod
    def _require_database(database: InMemoryDatabase | None) -> InMemoryDatabase:
        if database is None:
            raise RuntimeError("Unit of work is not active")
        return database
