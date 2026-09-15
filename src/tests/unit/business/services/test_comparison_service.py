from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from procurepilot.business.entities import Part, Supplier, SupplierQuotation
from procurepilot.business.enums import Currency, PartStatus, SupplierStatus, Unit
from procurepilot.business.in_memory import InMemoryDatabase, InMemoryUnitOfWork
from procurepilot.business.query_models import ComparisonRequest
from procurepilot.business.services.comparison import ComparisonService
from procurepilot.business.value_objects import Money, PositiveQuantity

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def supplier(supplier_id: str, *, active: bool = True) -> Supplier:
    return Supplier(
        supplier_id=supplier_id,
        supplier_code=supplier_id.upper(),
        name=supplier_id,
        status=SupplierStatus.ACTIVE if active else SupplierStatus.INACTIVE,
    )


def quotation(
    quotation_id: str,
    supplier_id: str,
    price: str,
    *,
    lead_time_days: int = 5,
    currency: Currency = Currency.CNY,
    unit: Unit = Unit.PIECE,
    minimum: str = "1",
    expired: bool = False,
) -> SupplierQuotation:
    return SupplierQuotation(
        quotation_id=quotation_id,
        supplier_id=supplier_id,
        part_id="part-1",
        unit_price=Money(Decimal(price), currency),
        minimum_order_quantity=PositiveQuantity(Decimal(minimum), unit),
        lead_time_days=lead_time_days,
        valid_from=NOW - timedelta(days=10),
        valid_until=NOW - timedelta(days=1) if expired else NOW + timedelta(days=10),
        source="test",
        collected_at=NOW,
    )


async def seed(database: InMemoryDatabase, *quotes: SupplierQuotation) -> None:
    async with InMemoryUnitOfWork(database) as uow:
        await uow.parts.add(
            Part("part-1", "P-1", "Part", "spec", Unit.PIECE, PartStatus.ACTIVE)
        )
        for supplier_id in {quote.supplier_id for quote in quotes}:
            await uow.suppliers.add(supplier(supplier_id, active=supplier_id != "disabled"))
        for quote in quotes:
            await uow.quotations.add(quote)
        await uow.commit()


def request() -> ComparisonRequest:
    return ComparisonRequest(
        part_id="part-1",
        quantity=PositiveQuantity(Decimal("10"), Unit.PIECE),
        currency=Currency.CNY,
    )


@pytest.mark.asyncio
async def test_no_quotation_returns_empty_comparison() -> None:
    database = InMemoryDatabase()
    await seed(database)

    result = await ComparisonService(lambda: InMemoryUnitOfWork(database)).compare_suppliers(
        request(), NOW
    )

    assert result.candidates == ()
    assert result.excluded == ()


@pytest.mark.asyncio
async def test_invalid_quotations_are_excluded_with_explicit_reasons() -> None:
    database = InMemoryDatabase()
    await seed(
        database,
        quotation("expired", "supplier-1", "10", expired=True),
        quotation("moq", "supplier-2", "9", minimum="20"),
        quotation("currency", "supplier-3", "8", currency=Currency.USD),
        quotation("unit", "supplier-4", "7", unit=Unit.KILOGRAM),
        quotation("disabled", "disabled", "6"),
    )

    result = await ComparisonService(lambda: InMemoryUnitOfWork(database)).compare_suppliers(
        request(), NOW
    )

    assert result.candidates == ()
    assert {item.quotation_id: item.reason for item in result.excluded} == {
        "expired": "quotation_expired",
        "moq": "minimum_order_quantity_not_met",
        "currency": "currency_mismatch",
        "unit": "unit_mismatch",
        "disabled": "supplier_inactive",
    }


@pytest.mark.asyncio
async def test_candidates_are_sorted_by_price_then_lead_time() -> None:
    database = InMemoryDatabase()
    await seed(
        database,
        quotation("slow", "supplier-1", "8", lead_time_days=10),
        quotation("fast", "supplier-2", "8", lead_time_days=3),
        quotation("expensive", "supplier-3", "9", lead_time_days=1),
    )

    result = await ComparisonService(lambda: InMemoryUnitOfWork(database)).compare_suppliers(
        request(), NOW
    )

    assert [item.quotation.quotation_id for item in result.candidates] == [
        "fast",
        "slow",
        "expensive",
    ]
