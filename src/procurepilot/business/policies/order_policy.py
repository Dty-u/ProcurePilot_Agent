"""Allowed purchase-order state transitions."""

from procurepilot.business.enums import OrderStatus
from procurepilot.business.errors import InvalidOrderStateError

_ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.DRAFT: frozenset({OrderStatus.PENDING_APPROVAL}),
    OrderStatus.PENDING_APPROVAL: frozenset({OrderStatus.APPROVED, OrderStatus.REJECTED}),
    OrderStatus.APPROVED: frozenset({OrderStatus.CREATED}),
    OrderStatus.CREATED: frozenset({OrderStatus.CANCELLED}),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}


def ensure_order_transition(current: OrderStatus, target: OrderStatus) -> None:
    """Raise when an order cannot move directly to the requested status."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidOrderStateError(
            f"Order cannot transition from {current.value} to {target.value}"
        )
