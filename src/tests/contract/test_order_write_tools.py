from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from mcp_server.context import ToolCallerContext
from mcp_server.tools.order_tools import (
    OrderCancelInput,
    OrderCreateInput,
    OrderUpdateInput,
    order_cancel,
    order_create,
    order_update,
)
from procurepilot.business.enums import Currency, OrderStatus
from procurepilot.business.services.order import ExecuteSavedOperationRequest


class SpyOrderWriteService:
    def __init__(self) -> None:
        self.calls: list[ExecuteSavedOperationRequest] = []

    async def execute_saved(self, request: ExecuteSavedOperationRequest, context: Any) -> Any:
        self.calls.append(request)
        return type(
            "Order",
            (),
            {
                "order_id": "order-1",
                "order_no": "PO-1",
                "status": OrderStatus.CREATED,
                "currency": Currency.CNY,
                "version": 1,
            },
        )()


def caller() -> ToolCallerContext:
    return ToolCallerContext(
        user_id="user-1",
        roles=frozenset({"order_executor"}),
        trace_id="trace-1",
        thread_id="thread-1",
    )


def test_write_inputs_forbid_business_payload_replacement() -> None:
    with pytest.raises(ValidationError):
        OrderCreateInput(
            operation_id="operation-1",
            approval_id="approval-1",
            idempotency_key="idem-1",
            supplier_id="attacker",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function", "input_value", "expected_version"),
    [
        (
            order_create,
            OrderCreateInput(
                operation_id="operation-1",
                approval_id="approval-1",
                idempotency_key="idem-1",
            ),
            None,
        ),
        (
            order_update,
            OrderUpdateInput(
                operation_id="operation-1",
                approval_id="approval-1",
                idempotency_key="idem-1",
                expected_version=2,
            ),
            2,
        ),
        (
            order_cancel,
            OrderCancelInput(
                operation_id="operation-1",
                approval_id="approval-1",
                idempotency_key="idem-1",
                expected_version=2,
            ),
            2,
        ),
    ],
)
async def test_write_tools_only_forward_execution_references(
    function: Any,
    input_value: Any,
    expected_version: int | None,
) -> None:
    service = SpyOrderWriteService()

    result = await function(
        input_value,
        service=service,
        caller=caller(),
        timeout_seconds=1,
        now=lambda: datetime(2026, 9, 9, tzinfo=UTC),
        audit_id_factory=lambda: "audit-1",
    )

    assert result.ok is True
    assert service.calls[0].expected_version == expected_version
    assert set(service.calls[0].__dataclass_fields__) == {
        "operation_id",
        "approval_id",
        "idempotency_key",
        "audit_id",
        "executed_at",
        "expected_version",
    }
