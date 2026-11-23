"""采购领域对象使用的有限枚举值。"""

from enum import StrEnum


class Currency(StrEnum):
    CNY = "CNY"
    USD = "USD"
    EUR = "EUR"
    JPY = "JPY"


class SupplierStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class PartStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class OrderStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CREATED = "created"
    CANCELLED = "cancelled"


class OrderAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    CANCEL = "cancel"


class Unit(StrEnum):
    PIECE = "piece"
    KILOGRAM = "kg"
    METER = "m"
    LITER = "l"
