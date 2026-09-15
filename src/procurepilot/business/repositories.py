"""Storage-agnostic repository and transaction contracts."""

from datetime import datetime
from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from procurepilot.business.approval import ApprovalGrant
from procurepilot.business.entities import (
    InventoryItem,
    OperationAudit,
    Part,
    PurchaseOrder,
    Supplier,
    SupplierQuotation,
)
from procurepilot.business.order_operations import OrderOperation
from procurepilot.business.query_models import (
    InventorySearchCriteria,
    OrderSearchCriteria,
    PartSearchCriteria,
    QuotationSearchCriteria,
    SupplierSearchCriteria,
)


@runtime_checkable
class SupplierRepository(Protocol):
    async def get_by_id(self, supplier_id: str) -> Supplier | None: ...
    async def search(self, criteria: SupplierSearchCriteria) -> list[Supplier]: ...
    async def add(self, supplier: Supplier) -> None: ...


@runtime_checkable
class PartRepository(Protocol):
    async def get_by_id(self, part_id: str) -> Part | None: ...
    async def search(self, criteria: PartSearchCriteria) -> list[Part]: ...
    async def add(self, part: Part) -> None: ...


@runtime_checkable
class QuotationRepository(Protocol):
    async def get_by_id(self, quotation_id: str) -> SupplierQuotation | None: ...
    async def search(self, criteria: QuotationSearchCriteria) -> list[SupplierQuotation]: ...
    async def add(self, quotation: SupplierQuotation) -> None: ...


@runtime_checkable
class InventoryRepository(Protocol):
    async def get_by_id(self, inventory_id: str) -> InventoryItem | None: ...
    async def search(self, criteria: InventorySearchCriteria) -> list[InventoryItem]: ...
    async def add(self, item: InventoryItem) -> None: ...


@runtime_checkable
class OrderRepository(Protocol):
    async def get_by_id(self, order_id: str) -> PurchaseOrder | None: ...
    async def get_by_idempotency_key(self, idempotency_key: str) -> PurchaseOrder | None: ...
    async def search(self, criteria: OrderSearchCriteria) -> list[PurchaseOrder]: ...
    async def add(self, order: PurchaseOrder) -> None: ...
    async def update(self, order: PurchaseOrder, *, expected_version: int) -> None: ...


@runtime_checkable
class ApprovalRepository(Protocol):
    async def is_approved(self, *, operation_id: str, actor_id: str) -> bool: ...
    async def consume(self, *, operation_id: str, actor_id: str, at: datetime) -> None: ...


@runtime_checkable
class BoundApprovalRepository(ApprovalRepository, Protocol):
    async def get_by_id(self, approval_id: str) -> ApprovalGrant | None: ...
    async def add(self, approval: ApprovalGrant) -> None: ...
    async def update(self, approval: ApprovalGrant) -> None: ...


@runtime_checkable
class OrderOperationRepository(Protocol):
    async def get_by_id(self, operation_id: str) -> OrderOperation | None: ...
    async def add(self, operation: OrderOperation) -> None: ...
    async def update(self, operation: OrderOperation) -> None: ...


@runtime_checkable
class AuditRepository(Protocol):
    async def add(self, audit: OperationAudit) -> None: ...
    async def list_for_object(self, object_id: str) -> list[OperationAudit]: ...


@runtime_checkable
class UnitOfWork(Protocol):
    suppliers: SupplierRepository
    parts: PartRepository
    quotations: QuotationRepository
    inventory: InventoryRepository
    orders: OrderRepository
    approvals: BoundApprovalRepository
    operations: OrderOperationRepository
    audits: AuditRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
