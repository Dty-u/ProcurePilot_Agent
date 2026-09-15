from __future__ import annotations

from typing import Any

import pytest
from langchain.tools import ToolRuntime
from langchain_core.tools import ToolException

from agent.context import ProcurementContext
from agent.tools.procurement_order import (
    MCPProcurementOrderGateway,
    create_procurement_order_tools,
)
from agent.toolsets import ORDER_TOOL_NAMES
from mcp_server.schemas import ToolEnvelope, ToolError


def runtime_for(context: ProcurementContext) -> ToolRuntime:
    return ToolRuntime(
        state={},
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="call-order-1",
        store=None,
    )


def order_context() -> ProcurementContext:
    return ProcurementContext(
        user_id="user-1",
        roles=frozenset({"procurement_reader", "order_reader", "order_executor"}),
        thread_id="thread-1",
        trace_id="trace-1",
    )


class RecordingGateway:
    def __init__(self, *, succeed: bool = True) -> None:
        self.succeed = succeed
        self.calls: list[tuple[str, dict[str, Any], ProcurementContext]] = []

    async def call_tool(self, tool_name, arguments, context):
        self.calls.append((tool_name, arguments, context))
        if not self.succeed:
            return ToolEnvelope(
                ok=False,
                data=None,
                error=ToolError(
                    code="CONFLICT",
                    message="Order operation conflict",
                    retryable=False,
                ),
                trace_id=context.trace_id,
            )
        return ToolEnvelope(
            ok=True,
            data={"tool": tool_name},
            error=None,
            trace_id=context.trace_id,
        )


def test_order_agent_exposes_exactly_eight_approved_tools() -> None:
    tools = create_procurement_order_tools(RecordingGateway(), trusted_context=order_context())

    assert len(tools) == 8
    assert {tool.name for tool in tools} == ORDER_TOOL_NAMES
    for order_tool in tools:
        rendered = str(order_tool.tool_call_schema.model_json_schema())
        for protected_field in ("user_id", "roles", "thread_id", "trace_id"):
            assert protected_field not in rendered


@pytest.mark.asyncio
async def test_order_query_and_write_use_mcp_gateway_with_trusted_context() -> None:
    gateway = RecordingGateway()
    context = order_context()
    tools = {
        tool.name: tool
        for tool in create_procurement_order_tools(gateway, trusted_context=context)
    }

    await tools["supplier_query"].ainvoke(
        {"request": {"keyword": "供应商"}, "runtime": runtime_for(context)}
    )
    await tools["order_create"].ainvoke(
        {
            "request": {
                "operation_id": "operation-1",
                "approval_id": "approval-1",
                "idempotency_key": "idem-1",
            },
            "runtime": runtime_for(context),
        }
    )

    assert [call[0] for call in gateway.calls] == ["supplier_query", "order_create"]
    assert gateway.calls[1][1] == {
        "request": {
            "operation_id": "operation-1",
            "approval_id": "approval-1",
            "idempotency_key": "idem-1",
        }
    }
    assert all(call[2] is context for call in gateway.calls)


@pytest.mark.asyncio
async def test_real_order_gateway_calls_mcp_client() -> None:
    context = order_context()

    class Result:
        is_error = False
        structured_content = {
            "ok": True,
            "data": {"order_id": "order-1"},
            "error": None,
            "trace_id": context.trace_id,
        }

    class Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, Any]]] = []

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return Result()

    client = Client()
    gateway = MCPProcurementOrderGateway(client, bound_context=context)
    tool = next(
        item
        for item in create_procurement_order_tools(gateway, trusted_context=context)
        if item.name == "order_create"
    )

    result = await tool.ainvoke(
        {
            "request": {
                "operation_id": "operation-1",
                "approval_id": "approval-1",
                "idempotency_key": "idem-1",
            },
            "runtime": runtime_for(context),
        }
    )

    assert '"ok":true' in result
    assert client.calls == [
        (
            "order_create",
            {
                "request": {
                    "operation_id": "operation-1",
                    "approval_id": "approval-1",
                    "idempotency_key": "idem-1",
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_model_cannot_override_trusted_identity() -> None:
    gateway = RecordingGateway()
    context = order_context()
    tool = next(
        item
        for item in create_procurement_order_tools(gateway, trusted_context=context)
        if item.name == "supplier_query"
    )

    result = await tool.ainvoke(
        {
            "request": {"keyword": "供应商"},
            "user_id": "attacker",
            "roles": ["admin"],
            "thread_id": "other-thread",
            "trace_id": "other-trace",
            "runtime": runtime_for(context),
        }
    )

    assert '"ok":true' in result
    assert len(gateway.calls) == 1
    assert gateway.calls[0][0] == "supplier_query"
    assert gateway.calls[0][1]["request"]["keyword"] == "供应商"
    assert not {
        "user_id",
        "roles",
        "thread_id",
        "trace_id",
    }.intersection(gateway.calls[0][1]["request"])
    assert gateway.calls[0][2] is context


@pytest.mark.asyncio
async def test_failed_write_envelope_raises_tool_exception_without_retry() -> None:
    gateway = RecordingGateway(succeed=False)
    context = order_context()
    tool = next(
        item
        for item in create_procurement_order_tools(gateway, trusted_context=context)
        if item.name == "order_cancel"
    )
    tool.handle_tool_error = False

    with pytest.raises(ToolException, match=r"Tool failed \[CONFLICT\]"):
        await tool.ainvoke(
            {
                "request": {
                    "operation_id": "operation-1",
                    "approval_id": "approval-1",
                    "idempotency_key": "idem-1",
                    "expected_version": 2,
                },
                "runtime": runtime_for(context),
            }
        )

    assert len(gateway.calls) == 1
