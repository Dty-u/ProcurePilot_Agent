"""受约束采购下单工具集的 Agent 侧 MCP 适配器。"""

from typing import Any, Protocol

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, tool

from agent.context import ProcurementContext
from agent.subagents.order_info import (
    OrderDraft,
    apply_order_supplement,
    build_info_request,
)
from agent.tools.procurement_read import MCPProcurementReadGateway, invoke_mcp_tool
from mcp_server.schemas import ToolEnvelope
from mcp_server.tools.order_tools import (
    OrderCancelInput,
    OrderCreateInput,
    OrderSearchDetailsInput,
    OrderUpdateInput,
)
from mcp_server.tools.parts_tools import PartQueryInput
from mcp_server.tools.suppliers_tools import QuotationQueryInput, SupplierQueryInput


class ProcurementOrderGateway(Protocol):
    """下单工具使用的可信 MCP 桥接，绝不暴露调用方身份。"""

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ProcurementContext,
    ) -> ToolEnvelope[Any]: ...


class MCPProcurementOrderGateway(MCPProcurementReadGateway):
    """同一严格 MCP 响应封装与上下文边界的下单专用命名。"""


def create_procurement_order_tools(
    gateway: ProcurementOrderGateway,
    *,
    trusted_context: ProcurementContext | None = None,
) -> list[BaseTool]:
    """严格创建采购下单 Agent 获准使用的八个工具。"""

    @tool("supplier_query")
    async def supplier_query_tool(
        request: SupplierQueryInput,
        runtime: ToolRuntime[ProcurementContext],
    ) -> str:
        """按关键词和状态查询供应商。"""
        return await invoke_mcp_tool(
            gateway, "supplier_query", request, runtime, trusted_context=trusted_context
        )

    @tool("part_query")
    async def part_query_tool(
        request: PartQueryInput,
        runtime: ToolRuntime[ProcurementContext],
    ) -> str:
        """按关键词、状态和单位查询物料。"""
        return await invoke_mcp_tool(
            gateway, "part_query", request, runtime, trusted_context=trusted_context
        )

    @tool("quotation_query")
    async def quotation_query_tool(
        request: QuotationQueryInput,
        runtime: ToolRuntime[ProcurementContext],
    ) -> str:
        """查询有效报价及其来源证据。"""
        return await invoke_mcp_tool(
            gateway, "quotation_query", request, runtime, trusted_context=trusted_context
        )

    @tool("order_search_details")
    async def order_search_details_tool(
        request: OrderSearchDetailsInput,
        runtime: ToolRuntime[ProcurementContext],
    ) -> str:
        """查询采购订单及其乐观锁版本号。"""
        return await invoke_mcp_tool(
            gateway,
            "order_search_details",
            request,
            runtime,
            trusted_context=trusted_context,
        )

    @tool("request_order_info")
    async def request_order_info_tool(
        request: OrderDraft,
        runtime: ToolRuntime[ProcurementContext],
    ) -> str:
        """暂停订单流程，请用户补充缺失的结构化字段。"""
        del runtime
        info_request = build_info_request(request)
        if not info_request.missing_fields:
            return request.model_dump_json()

        from langgraph.types import interrupt

        resume = interrupt(info_request.model_dump(mode="json"))
        if not isinstance(resume, dict):
            raise ValueError("order supplement resume must be an object")
        return apply_order_supplement(request, resume).model_dump_json()

    @tool("order_create")
    async def order_create_tool(
        request: OrderCreateInput,
        runtime: ToolRuntime[ProcurementContext],
    ) -> str:
        """执行已保存且已批准的订单创建操作；失败时不得自动重试。"""
        return await invoke_mcp_tool(
            gateway, "order_create", request, runtime, trusted_context=trusted_context
        )

    @tool("order_update")
    async def order_update_tool(
        request: OrderUpdateInput,
        runtime: ToolRuntime[ProcurementContext],
    ) -> str:
        """执行已保存且已批准的订单更新操作；失败时不得自动重试。"""
        return await invoke_mcp_tool(
            gateway, "order_update", request, runtime, trusted_context=trusted_context
        )

    @tool("order_cancel")
    async def order_cancel_tool(
        request: OrderCancelInput,
        runtime: ToolRuntime[ProcurementContext],
    ) -> str:
        """执行已保存且已批准的订单取消操作；失败时不得自动重试。"""
        return await invoke_mcp_tool(
            gateway, "order_cancel", request, runtime, trusted_context=trusted_context
        )

    order_tools = [
        supplier_query_tool,
        part_query_tool,
        quotation_query_tool,
        order_search_details_tool,
        request_order_info_tool,
        order_create_tool,
        order_update_tool,
        order_cancel_tool,
    ]
    for order_tool in order_tools:
        order_tool.handle_tool_error = True
    return order_tools
