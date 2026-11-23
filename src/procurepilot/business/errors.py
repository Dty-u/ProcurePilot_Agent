"""确定性采购规则抛出的显式错误。"""


class DomainError(Exception):
    """采购领域错误的基类。"""


class DomainValidationError(DomainError, ValueError):
    """领域对象将违反其不变量。"""


class InactiveEntityError(DomainError):
    """采购中使用了已停用的供应商或物料。"""


class CurrencyMismatchError(DomainError):
    """不同币种的金额被合并计算。"""


class InvalidOrderStateError(DomainError):
    """不允许的订单状态流转。"""


class ImmutableOrderError(DomainError):
    """已处于终态的订单被修改。"""


class EntityNotFoundError(DomainError):
    """请求的业务实体不存在。"""


class ConflictError(DomainError):
    """发生唯一性、幂等性或乐观锁版本冲突。"""


class PermissionDeniedError(DomainError):
    """当前操作者无权执行该操作。"""


class ApprovalRequiredError(DomainError):
    """受保护的写操作缺少有效审批。"""


class InfrastructureError(DomainError):
    """基础设施操作失败，且不暴露实现细节。"""
