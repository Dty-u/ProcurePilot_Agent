from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from procurepilot.business.enums import Currency, Unit
from procurepilot.business.value_objects import Money, PositiveQuantity, ensure_utc


def test_currency_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        Currency("GBP")


def test_money_rejects_float() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        Money(amount=12.3, currency=Currency.CNY)  # type: ignore[arg-type]


def test_money_quantizes_to_currency_precision() -> None:
    assert Money(Decimal("12.345"), Currency.CNY).amount == Decimal("12.35")
    assert Money(Decimal("12.5"), Currency.JPY).amount == Decimal("13")


def test_money_addition_is_exact() -> None:
    total = Money(Decimal("0.1"), Currency.CNY) + Money(Decimal("0.2"), Currency.CNY)

    assert total == Money(Decimal("0.30"), Currency.CNY)


def test_money_cannot_add_different_currencies() -> None:
    with pytest.raises(ValueError, match="currency"):
        Money(Decimal("1"), Currency.CNY) + Money(Decimal("1"), Currency.USD)


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1")])
def test_positive_quantity_must_be_greater_than_zero(amount: Decimal) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        PositiveQuantity(amount=amount, unit=Unit.PIECE)


def test_positive_quantity_rejects_float() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        PositiveQuantity(amount=1.5, unit=Unit.KILOGRAM)  # type: ignore[arg-type]


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ensure_utc(datetime(2026, 9, 8, 12, 0))


def test_aware_datetime_is_normalized_to_utc() -> None:
    china_timezone = timezone(timedelta(hours=8))

    normalized = ensure_utc(datetime(2026, 9, 8, 12, 0, tzinfo=china_timezone))

    assert normalized == datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
    assert normalized.tzinfo is UTC
