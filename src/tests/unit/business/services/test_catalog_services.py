from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from procurepilot.business.entities import InventoryItem, Part, Supplier, SupplierQuotation
from procurepilot.business.enums import Currency, PartStatus, SupplierStatus, Unit
from procurepilot.business.in_memory import InMemoryDatabase, InMemoryUnitOfWork
from procurepilot.business.query_models import (
    InventorySearchCriteria,
    PartSearchCriteria,
    QuotationSearchCriteria,
    SupplierSearchCriteria,
)
from procurepilot.business.services.catalog import (
    InventoryService,
    PartService,
    QuotationService,
    SupplierService,
)
from procurepilot.business.value_objects import Money, PositiveQuantity

NOW = datetime(2026, 9, 8, tzinfo=UTC)


@pytest.mark.asyncio
async def test_catalog_services_filter_valid_quotes_and_inventory_warnings() -> None:
    database = InMemoryDatabase()
    async with InMemoryUnitOfWork(database) as uow:
        await uow.suppliers.add(
            Supplier("supplier-1", "S-1", "Alpha Supplier", SupplierStatus.ACTIVE)
        )
        await uow.parts.add(
            Part("part-1", "P-1", "Bearing", "spec", Unit.PIECE, PartStatus.ACTIVE)
        )
        for quotation_id, valid_until in (
            ("valid", NOW + timedelta(days=1)),
            ("expired", NOW - timedelta(days=1)),
        ):
            await uow.quotations.add(
                SupplierQuotation(
                    quotation_id=quotation_id,
                    supplier_id="supplier-1",
                    part_id="part-1",
                    unit_price=Money(Decimal("10"), Currency.CNY),
                    minimum_order_quantity=PositiveQuantity(Decimal("1"), Unit.PIECE),
                    lead_time_days=3,
                    valid_from=NOW - timedelta(days=2),
                    valid_until=valid_until,
                    source="test",
                    collected_at=NOW,
                )
            )
        await uow.inventory.add(
            InventoryItem(
                "inventory-1",
                "part-1",
                "WH-1",
                Unit.PIECE,
                Decimal("10"),
                Decimal("6"),
                Decimal("5"),
            )
        )
        await uow.commit()

    def factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(database)

    suppliers = await SupplierService(factory).search(SupplierSearchCriteria(keyword="alpha"))
    parts = await PartService(factory).search(PartSearchCriteria(keyword="bearing"))
    quotations = await QuotationService(factory).find_valid_quotes(
        QuotationSearchCriteria(part_id="part-1"), NOW
    )
    warnings = await InventoryService(factory).get_warnings(
        InventorySearchCriteria(part_id="part-1")
    )

    assert [supplier.supplier_id for supplier in suppliers] == ["supplier-1"]
    assert [part.part_id for part in parts] == ["part-1"]
    assert [quotation.quotation_id for quotation in quotations] == ["valid"]
    assert [item.inventory_id for item in warnings] == ["inventory-1"]
