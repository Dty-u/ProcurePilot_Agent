"""Validated order-operation snapshots and stable approval hashes."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator

from procurepilot.business.enums import Currency, OrderAction, Unit
from procurepilot.business.value_objects import ensure_utc


class OperationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OrderLinePayload(OperationPayload):
    order_item_id: str = Field(min_length=1, max_length=64)
    part_id: str = Field(min_length=1, max_length=64)
    quotation_id: str = Field(min_length=1, max_length=64)
    quantity: Decimal = Field(gt=0)
    unit: Unit


class CreateOrderPayload(OperationPayload):
    order_id: str = Field(min_length=1, max_length=64)
    order_no: str = Field(min_length=1, max_length=64)
    supplier_id: str = Field(min_length=1, max_length=64)
    currency: Currency
    requested_at: datetime
    items: tuple[OrderLinePayload, ...] = Field(min_length=1)

    @field_validator("requested_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class UpdateOrderPayload(OperationPayload):
    target_order_id: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=1)
    requested_at: datetime
    items: tuple[OrderLinePayload, ...] = Field(min_length=1)

    @field_validator("requested_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class CancelOrderPayload(OperationPayload):
    target_order_id: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=1)


OrderPayload: TypeAlias = CreateOrderPayload | UpdateOrderPayload | CancelOrderPayload
OperationStatus = Literal["pending_approval", "approved", "rejected", "executed"]


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump())
    if isinstance(value, dict):
        return {key: _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return format(normalized, "f")
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    return value


def normalized_payload(payload: OrderPayload) -> dict[str, Any]:
    result = _canonicalize(payload)
    assert isinstance(result, dict)
    return result


def compute_payload_hash(payload: OrderPayload) -> str:
    encoded = json.dumps(
        normalized_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class OrderOperation:
    operation_id: str
    action: OrderAction
    user_id: str
    thread_id: str
    normalized_payload: dict[str, Any]
    payload_hash: str
    status: OperationStatus
    created_at: datetime
    expires_at: datetime

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        action: OrderAction,
        user_id: str,
        thread_id: str,
        payload: OrderPayload,
        created_at: datetime,
        expires_at: datetime,
    ) -> "OrderOperation":
        created = ensure_utc(created_at)
        expires = ensure_utc(expires_at)
        if expires <= created:
            raise ValueError("operation expiry must be after creation")
        return cls(
            operation_id=operation_id,
            action=action,
            user_id=user_id,
            thread_id=thread_id,
            normalized_payload=normalized_payload(payload),
            payload_hash=compute_payload_hash(payload),
            status="pending_approval",
            created_at=created,
            expires_at=expires,
        )

    def parse_payload(self) -> OrderPayload:
        if self.action is OrderAction.CREATE:
            return CreateOrderPayload.model_validate(self.normalized_payload)
        if self.action is OrderAction.UPDATE:
            return UpdateOrderPayload.model_validate(self.normalized_payload)
        return CancelOrderPayload.model_validate(self.normalized_payload)

    def with_status(self, status: OperationStatus) -> "OrderOperation":
        return OrderOperation(
            operation_id=self.operation_id,
            action=self.action,
            user_id=self.user_id,
            thread_id=self.thread_id,
            normalized_payload=self.normalized_payload,
            payload_hash=self.payload_hash,
            status=status,
            created_at=self.created_at,
            expires_at=self.expires_at,
        )
