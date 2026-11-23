"""与参数绑定、会过期且一次性的订单审批授权。"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from procurepilot.business.enums import OrderAction
from procurepilot.business.errors import (
    ApprovalRequiredError,
    ConflictError,
    PermissionDeniedError,
)
from procurepilot.business.value_objects import ensure_utc

ApprovalDecision = Literal["approve", "reject"]


@dataclass(frozen=True, slots=True)
class ApprovalGrant:
    approval_id: str
    operation_id: str
    approver_user_id: str
    thread_id: str
    action: OrderAction
    payload_hash: str
    decision: ApprovalDecision
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    def __post_init__(self) -> None:
        for value in (
            self.approval_id,
            self.operation_id,
            self.approver_user_id,
            self.thread_id,
        ):
            if not value.strip():
                raise ValueError("approval identifiers must not be empty")
        if len(self.payload_hash) != 64:
            raise ValueError("payload_hash must be SHA-256 hex")
        created = ensure_utc(self.created_at)
        expires = ensure_utc(self.expires_at)
        consumed = None if self.consumed_at is None else ensure_utc(self.consumed_at)
        if expires <= created:
            raise ValueError("approval expiry must be after creation")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "consumed_at", consumed)

    def authorize_and_consume(
        self,
        *,
        operation_id: str,
        user_id: str,
        thread_id: str,
        action: OrderAction,
        payload_hash: str,
        at: datetime,
    ) -> "ApprovalGrant":
        checked_at = ensure_utc(at)
        if self.decision != "approve":
            raise ApprovalRequiredError("order operation was rejected")
        if checked_at >= self.expires_at:
            raise ApprovalRequiredError("order approval expired")
        if self.consumed_at is not None:
            raise ConflictError("order approval was already consumed")
        if self.approver_user_id != user_id or self.thread_id != thread_id:
            raise PermissionDeniedError("order approval identity scope mismatch")
        if self.operation_id != operation_id:
            raise ConflictError("order approval operation mismatch")
        if self.action is not action or self.payload_hash != payload_hash:
            raise ConflictError("order approval no longer matches operation parameters")
        return replace(self, consumed_at=checked_at)
