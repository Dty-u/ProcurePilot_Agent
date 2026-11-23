"""允许的采购订单状态流转。"""

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
    """订单无法直接流转到目标状态时抛出异常。"""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidOrderStateError(
            f"Order cannot transition from {current.value} to {target.value}"
        )
