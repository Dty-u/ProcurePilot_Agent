"""只读采购订单 MCP 工具适配器。"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mcp_server.context import ToolCallerContext
from mcp_server.error_mapper import error_envelope
from mcp_server.schemas import StrictInput, ToolEnvelope
from procurepilot.business.entities import PurchaseOrder
from procurepilot.business.enums import Currency, OrderStatus, Unit
from procurepilot.business.errors import PermissionDeniedError
from procurepilot.business.query_models import OrderSearchCriteria
from procurepilot.business.services.order import ActorContext, ExecuteSavedOperationRequest


class OrderSearchDetailsInput(StrictInput):
    order_id: str | None = Field(default=None, min_length=1, max_length=128)
    order_no: str | None = Field(default=None, min_length=1, max_length=128)
    supplier_id: str | None = Field(default=None, min_length=1, max_length=128)
    status: OrderStatus | None = None
    limit: int = Field(default=20, ge=1, le=50)


class OrderItemResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_item_id: str
    part_id: str
    quantity: Decimal
    unit: Unit
    unit_price: Decimal
    currency: Currency
    quotation_id: str | None


class OrderResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    order_no: str
    supplier_id: str
    status: OrderStatus
    currency: Currency
    total_amount: Decimal
    version: int
    items: list[OrderItemResult]


class OrderSearcher(Protocol):
    async def search(self, criteria: OrderSearchCriteria) -> list[PurchaseOrder]: ...


async def order_search_details(
    request: OrderSearchDetailsInput,
    *,
    service: OrderSearcher,
    caller: ToolCallerContext,
    timeout_seconds: float,
) -> ToolEnvelope[list[OrderResult]]:
    try:
        if not caller.roles.intersection({"order_reader", "admin"}):
            raise PermissionDeniedError("role required: order_reader")
        orders = await asyncio.wait_for(
            service.search(
                OrderSearchCriteria(
                    order_id=request.order_id,
                    order_no=request.order_no,
                    supplier_id=request.supplier_id,
                    status=request.status,
                    limit=request.limit,
                )
            ),
            timeout_seconds,
        )
        data = [
            OrderResult(
                order_id=order.order_id,
                order_no=order.order_no,
                supplier_id=order.supplier_id,
                status=order.status,
                currency=order.currency,
                total_amount=order.total_amount.amount,
                version=order.version,
                items=[
                    OrderItemResult(
                        order_item_id=item.order_item_id,
                        part_id=item.part_id,
                        quantity=item.quantity.amount,
                        unit=item.quantity.unit,
                        unit_price=item.unit_price.amount,
                        currency=item.unit_price.currency,
                        quotation_id=item.quotation_id,
                    )
                    for item in order.items
                ],
            )
            for order in orders[: request.limit]
        ]
        return ToolEnvelope(ok=True, data=data, error=None, trace_id=caller.trace_id)
    except Exception as error:
        return error_envelope(error, trace_id=caller.trace_id)  # type: ignore[return-value]


class OrderCreateInput(StrictInput):
    operation_id: str = Field(min_length=1, max_length=64)
    approval_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)


class OrderUpdateInput(OrderCreateInput):
    expected_version: int = Field(ge=1)


class OrderCancelInput(OrderCreateInput):
    expected_version: int = Field(ge=1)


class OrderWriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    order_id: str
    order_no: str
    status: OrderStatus
    currency: Currency
    version: int


class OrderWriteService(Protocol):
    async def execute_saved(
        self,
        request: ExecuteSavedOperationRequest,
        context: ActorContext,
    ) -> PurchaseOrder: ...


async def _execute(
    request: OrderCreateInput,
    *,
    expected_version: int | None,
    service: OrderWriteService,
    caller: ToolCallerContext,
    timeout_seconds: float,
    now: Callable[[], datetime],
    audit_id_factory: Callable[[], str],
) -> ToolEnvelope[OrderWriteResult]:
    try:
        actor = ActorContext(
            actor_id=caller.user_id,
            roles=frozenset(caller.roles),
            trace_id=caller.trace_id,
            thread_id=caller.thread_id,
        )
        order = await asyncio.wait_for(
            service.execute_saved(
                ExecuteSavedOperationRequest(
                    operation_id=request.operation_id,
                    approval_id=request.approval_id,
                    idempotency_key=request.idempotency_key,
                    audit_id=audit_id_factory(),
                    executed_at=now(),
                    expected_version=expected_version,
                ),
                actor,
            ),
            timeout_seconds,
        )
        return ToolEnvelope(
            ok=True,
            data=OrderWriteResult(
                order_id=order.order_id,
                order_no=order.order_no,
                status=order.status,
                currency=order.currency,
                version=order.version,
            ),
            error=None,
            trace_id=caller.trace_id,
        )
    except Exception as error:
        return error_envelope(error, trace_id=caller.trace_id)  # type: ignore[return-value]


async def order_create(
    request: OrderCreateInput,
    *,
    service: OrderWriteService,
    caller: ToolCallerContext,
    timeout_seconds: float,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    audit_id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> ToolEnvelope[OrderWriteResult]:
    return await _execute(
        request,
        expected_version=None,
        service=service,
        caller=caller,
        timeout_seconds=timeout_seconds,
        now=now,
        audit_id_factory=audit_id_factory,
    )


async def order_update(
    request: OrderUpdateInput,
    *,
    service: OrderWriteService,
    caller: ToolCallerContext,
    timeout_seconds: float,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    audit_id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> ToolEnvelope[OrderWriteResult]:
    return await _execute(
        request,
        expected_version=request.expected_version,
        service=service,
        caller=caller,
        timeout_seconds=timeout_seconds,
        now=now,
        audit_id_factory=audit_id_factory,
    )


async def order_cancel(
    request: OrderCancelInput,
    *,
    service: OrderWriteService,
    caller: ToolCallerContext,
    timeout_seconds: float,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    audit_id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> ToolEnvelope[OrderWriteResult]:
    return await _execute(
        request,
        expected_version=request.expected_version,
        service=service,
        caller=caller,
        timeout_seconds=timeout_seconds,
        now=now,
        audit_id_factory=audit_id_factory,
    )
