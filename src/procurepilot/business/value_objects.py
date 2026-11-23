"""金额、数量与时间的不可变值对象。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from procurepilot.business.enums import Currency, Unit

_CURRENCY_QUANTUM = {
    Currency.CNY: Decimal("0.01"),
    Currency.USD: Decimal("0.01"),
    Currency.EUR: Decimal("0.01"),
    Currency.JPY: Decimal("1"),
}


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money amount must be a Decimal")
        if not isinstance(self.currency, Currency):
            raise TypeError("Money currency must be a Currency")

        quantum = _CURRENCY_QUANTUM[self.currency]
        object.__setattr__(self, "amount", self.amount.quantize(quantum, ROUND_HALF_UP))

    def __add__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency is not other.currency:
            raise ValueError("Cannot add money with a different currency")
        return Money(self.amount + other.amount, self.currency)


@dataclass(frozen=True, slots=True)
class PositiveQuantity:
    amount: Decimal
    unit: Unit

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Quantity amount must be a Decimal")
        if not isinstance(self.unit, Unit):
            raise TypeError("Quantity unit must be a Unit")
        if self.amount <= 0:
            raise ValueError("Quantity amount must be greater than zero")


def ensure_utc(value: datetime) -> datetime:
    """要求带时区的 datetime，并统一转换为 UTC。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime must be timezone-aware")
    return value.astimezone(UTC)
