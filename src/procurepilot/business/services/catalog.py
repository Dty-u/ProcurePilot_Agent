"""Read-only catalog and inventory application services."""

from collections.abc import Callable
from datetime import datetime

from procurepilot.business.entities import (
    InventoryItem,
    Part,
    PurchaseOrder,
    Supplier,
    SupplierQuotation,
)
from procurepilot.business.query_models import (
    InventorySearchCriteria,
    OrderSearchCriteria,
    PartSearchCriteria,
    QuotationSearchCriteria,
    SupplierSearchCriteria,
)
from procurepilot.business.repositories import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


class SupplierService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def search(self, criteria: SupplierSearchCriteria) -> list[Supplier]:
        async with self._uow_factory() as uow:
            return await uow.suppliers.search(criteria)


class PartService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def search(self, criteria: PartSearchCriteria) -> list[Part]:
        async with self._uow_factory() as uow:
            return await uow.parts.search(criteria)

    async def find_by_supplier(
        self, supplier_id: str, *, at: datetime, limit: int
    ) -> list[Part]:
        """Return distinct parts backed by currently valid supplier quotations."""
        async with self._uow_factory() as uow:
            quotations = await uow.quotations.search(
                QuotationSearchCriteria(supplier_id=supplier_id, limit=500)
            )
            part_ids = list(
                dict.fromkeys(
                    quote.part_id for quote in quotations if quote.is_valid_at(at)
                )
            )[:limit]
            parts = [await uow.parts.get_by_id(part_id) for part_id in part_ids]
        return [part for part in parts if part is not None]


class QuotationService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def find_valid_quotes(
        self,
        criteria: QuotationSearchCriteria,
        at: datetime,
    ) -> list[SupplierQuotation]:
        async with self._uow_factory() as uow:
            quotations = await uow.quotations.search(criteria)
        return [quotation for quotation in quotations if quotation.is_valid_at(at)]


class InventoryService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def get_warnings(self, criteria: InventorySearchCriteria) -> list[InventoryItem]:
        async with self._uow_factory() as uow:
            inventory = await uow.inventory.search(criteria)
        return [item for item in inventory if item.available_quantity <= item.safety_stock]


class OrderQueryService:
    """Read-only purchase-order application service."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def search(self, criteria: OrderSearchCriteria) -> list[PurchaseOrder]:
        async with self._uow_factory() as uow:
            return await uow.orders.search(criteria)
