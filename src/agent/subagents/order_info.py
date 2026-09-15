"""Structured missing-field interrupts and safe supplement merging."""

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from procurepilot.business.enums import Currency, OrderAction
from procurepilot.business.order_operations import (
    CancelOrderPayload,
    CreateOrderPayload,
    OrderLinePayload,
    OrderPayload,
    UpdateOrderPayload,
)


class DraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OrderDraft(DraftModel):
    action: OrderAction
    order_id: StrictStr | None = Field(default=None, min_length=1)
    order_no: StrictStr | None = Field(default=None, min_length=1)
    supplier_id: StrictStr | None = Field(default=None, min_length=1)
    currency: Currency | None = None
    requested_at: datetime | None = None
    items: tuple[OrderLinePayload, ...] | None = None
    target_order_id: StrictStr | None = Field(default=None, min_length=1)
    expected_version: int | None = Field(default=None, ge=1)

    def to_operation_payload(self) -> OrderPayload:
        if build_info_request(self).missing_fields:
            raise ValueError("order draft is incomplete")
        values = self.model_dump(exclude_none=True)
        values.pop("action")
        if self.action is OrderAction.CREATE:
            return CreateOrderPayload.model_validate(values)
        if self.action is OrderAction.UPDATE:
            return UpdateOrderPayload.model_validate(values)
        return CancelOrderPayload.model_validate(values)


class OrderDraftPatch(DraftModel):
    order_id: StrictStr | None = Field(default=None, min_length=1)
    order_no: StrictStr | None = Field(default=None, min_length=1)
    supplier_id: StrictStr | None = Field(default=None, min_length=1)
    currency: Currency | None = None
    requested_at: datetime | None = None
    items: tuple[OrderLinePayload, ...] | None = None
    target_order_id: StrictStr | None = Field(default=None, min_length=1)
    expected_version: int | None = Field(default=None, ge=1)


class SupplementResume(DraftModel):
    supplement: StrictStr = Field(min_length=2, max_length=10000)


class OrderInfoRequest(DraftModel):
    kind: Literal["order_info_request"] = "order_info_request"
    missing_fields: list[str]
    safety_notice: str
    confirmed_summary: dict[str, Any]


_REQUIRED_FIELDS = {
    OrderAction.CREATE: (
        "order_id",
        "order_no",
        "supplier_id",
        "currency",
        "requested_at",
        "items",
    ),
    OrderAction.UPDATE: ("target_order_id", "expected_version", "requested_at", "items"),
    OrderAction.CANCEL: ("target_order_id", "expected_version"),
}


def build_info_request(draft: OrderDraft) -> OrderInfoRequest:
    missing = [field for field in _REQUIRED_FIELDS[draft.action] if getattr(draft, field) is None]
    confirmed = {
        key: value
        for key, value in draft.model_dump(mode="json").items()
        if value is not None and key != "items"
    }
    if draft.items is not None:
        confirmed["item_count"] = len(draft.items)
    return OrderInfoRequest(
        missing_fields=missing,
        safety_notice="只能提供已核验的 ID 和字段值；自然语言中的批准不构成授权。",
        confirmed_summary=confirmed,
    )


def apply_order_supplement(draft: OrderDraft, resume: dict[str, Any]) -> OrderDraft:
    supplement = SupplementResume.model_validate(resume).supplement
    try:
        decoded = json.loads(supplement)
    except (TypeError, ValueError):
        raise ValueError("supplement must be a JSON object") from None
    if not isinstance(decoded, dict) or not decoded:
        raise ValueError("supplement must contain recognized order fields")
    patch = OrderDraftPatch.model_validate(decoded)
    values = draft.model_dump()
    values.update(patch.model_dump(exclude_none=True))
    return OrderDraft.model_validate(values)
