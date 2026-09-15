from datetime import UTC, datetime

import pytest
from langchain.tools import ToolRuntime

from agent.context import ProcurementContext
from agent.tools.procurement_read import MCPProcurementReadGateway, create_procurement_read_tools
from mcp_server.schemas import ToolEnvelope, ToolError


def runtime_for(context: ProcurementContext) -> ToolRuntime:
    return ToolRuntime(
        state={},
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="call-1",
        store=None,
    )


class ContextAwareGateway:
    async def call_tool(self, tool_name, arguments, context):
        if context.user_id != "user-1" or context.trace_id != "trace-1":
            return ToolEnvelope(
                ok=False,
                data=None,
                error=ToolError(
                    code="PERMISSION_DENIED", message="Permission denied", retryable=False
                ),
                trace_id=context.trace_id,
            )
        return ToolEnvelope(
            ok=True,
            data=[{"tool": tool_name, "arguments": arguments}],
            error=None,
            trace_id=context.trace_id,
        )


def test_agent_exposes_only_six_read_tools_without_identity_arguments() -> None:
    tools = create_procurement_read_tools(ContextAwareGateway())

    assert {tool.name for tool in tools} == {
        "supplier_query",
        "part_query",
        "part_by_supplier",
        "quotation_query",
        "inventory_warning",
        "order_search_details",
    }
    for read_tool in tools:
        schema = read_tool.tool_call_schema.model_json_schema()
        rendered = str(schema)
        assert "user_id" not in rendered
        assert "roles" not in rendered


@pytest.mark.asyncio
async def test_runtime_context_is_injected_into_gateway() -> None:
    tool_by_name = {
        tool.name: tool for tool in create_procurement_read_tools(ContextAwareGateway())
    }
    context = ProcurementContext(
        user_id="user-1",
        roles=frozenset({"procurement_reader"}),
        trace_id="trace-1",
    )

    result = await tool_by_name["quotation_query"].ainvoke(
        {
            "request": {
                "part_id": "part-1",
                "at": datetime(2026, 9, 9, tzinfo=UTC).isoformat(),
            },
            "runtime": runtime_for(context),
        }
    )

    assert '"ok":true' in result
    assert '"tool":"quotation_query"' in result


@pytest.mark.asyncio
async def test_failed_envelope_becomes_safe_agent_tool_error() -> None:
    class FailedGateway:
        async def call_tool(self, tool_name, arguments, context):
            return ToolEnvelope(
                ok=False,
                data=None,
                error=ToolError(
                    code="DEPENDENCY_TIMEOUT",
                    message="Dependency timeout",
                    retryable=True,
                ),
                trace_id=context.trace_id,
            )

    tool_by_name = {tool.name: tool for tool in create_procurement_read_tools(FailedGateway())}
    context = ProcurementContext(
        user_id="user-1",
        roles=frozenset({"procurement_reader"}),
        trace_id="trace-1",
    )

    result = await tool_by_name["part_query"].ainvoke(
        {"request": {}, "runtime": runtime_for(context)}
    )

    assert result == "Tool failed [DEPENDENCY_TIMEOUT]: Dependency timeout; retryable=true"


@pytest.mark.asyncio
async def test_mcp_gateway_parses_structured_envelope_and_binds_identity() -> None:
    class Result:
        is_error = False
        structured_content = {
            "ok": True,
            "data": [{"supplier_id": "supplier-1"}],
            "error": None,
            "trace_id": "trace-1",
        }

    class Client:
        async def call_tool(self, name, arguments):
            return Result()

    context = ProcurementContext(
        user_id="user-1",
        roles=frozenset({"procurement_reader"}),
        trace_id="trace-1",
    )
    gateway = MCPProcurementReadGateway(Client(), bound_context=context)

    envelope = await gateway.call_tool("supplier_query", {"request": {}}, context)

    assert envelope.ok is True
    assert envelope.data == [{"supplier_id": "supplier-1"}]


@pytest.mark.asyncio
async def test_mcp_gateway_rejects_context_different_from_authenticated_binding() -> None:
    class Client:
        async def call_tool(self, name, arguments):
            raise AssertionError("untrusted context must not reach MCP")

    bound = ProcurementContext(
        user_id="user-1",
        roles=frozenset({"procurement_reader"}),
        trace_id="trace-1",
    )
    other = ProcurementContext(
        user_id="user-2",
        roles=frozenset({"procurement_reader"}),
        trace_id="trace-2",
    )
    gateway = MCPProcurementReadGateway(Client(), bound_context=bound)

    envelope = await gateway.call_tool("supplier_query", {"request": {}}, other)

    assert envelope.ok is False
    assert envelope.error is not None and envelope.error.code == "PERMISSION_DENIED"
