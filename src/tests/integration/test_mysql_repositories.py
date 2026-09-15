from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from procurepilot.business.entities import Part, Supplier, SupplierQuotation
from procurepilot.business.enums import Currency, PartStatus, SupplierStatus, Unit
from procurepilot.business.errors import ConflictError
from procurepilot.business.query_models import QuotationSearchCriteria, SupplierSearchCriteria
from procurepilot.business.value_objects import Money, PositiveQuantity
from procurepilot.infrastructure.mysql_uow import MySQLUnitOfWork

NOW = datetime(2026, 9, 8, tzinfo=UTC)


@pytest.mark.asyncio
async def test_mysql_repositories_round_trip_filter_limit_decimal_and_utc(
    mysql_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with MySQLUnitOfWork(mysql_session_factory) as uow:
        await uow.suppliers.add(Supplier("s-1", "S-1", "Alpha", SupplierStatus.ACTIVE))
        await uow.suppliers.add(Supplier("s-2", "S-2", "Beta", SupplierStatus.INACTIVE))
        await uow.parts.add(Part("p-1", "P-1", "Part", "spec", Unit.PIECE, PartStatus.ACTIVE))
        await uow.quotations.add(
            SupplierQuotation(
                "q-1",
                "s-1",
                "p-1",
                Money(Decimal("12.3456"), Currency.CNY),
                PositiveQuantity(Decimal("2.123456"), Unit.PIECE),
                3,
                NOW - timedelta(days=1),
                NOW + timedelta(days=1),
                "test",
                NOW,
            )
        )
        await uow.commit()

    async with MySQLUnitOfWork(mysql_session_factory) as uow:
        suppliers = await uow.suppliers.search(
            SupplierSearchCriteria(status=SupplierStatus.ACTIVE, limit=1)
        )
        quotes = await uow.quotations.search(QuotationSearchCriteria(part_id="p-1"))

    assert [supplier.supplier_id for supplier in suppliers] == ["s-1"]
    assert quotes[0].unit_price.amount == Decimal("12.35")
    assert quotes[0].minimum_order_quantity.amount == Decimal("2.123456")
    assert quotes[0].collected_at.tzinfo is UTC


@pytest.mark.asyncio
async def test_unique_constraint_is_mapped_to_stable_conflict(
    mysql_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with MySQLUnitOfWork(mysql_session_factory) as uow:
        await uow.suppliers.add(Supplier("s-1", "SAME", "Alpha", SupplierStatus.ACTIVE))
        await uow.commit()

    async with MySQLUnitOfWork(mysql_session_factory) as uow:
        await uow.suppliers.add(Supplier("s-2", "SAME", "Beta", SupplierStatus.ACTIVE))
        with pytest.raises(ConflictError, match="database uniqueness"):
            await uow.commit()
