"""六项只读采购 MCP 能力的 LangChain 适配器。"""

from typing import Any, Protocol

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, ToolException, tool
from pydantic import BaseModel

from agent.context import ProcurementContext
from mcp_server.schemas import ToolEnvelope, ToolError
from mcp_server.tools.inventory_tools import InventoryWarningInput
from mcp_server.tools.order_tools import OrderSearchDetailsInput
from mcp_server.tools.parts_tools import (
    PartBySupplierInput,
    PartQueryInput,
)
from mcp_server.tools.suppliers_tools import QuotationQueryInput, SupplierQueryInput


class ProcurementReadGateway(Protocol):
    """通往 MCP 只读层的可信桥接；身份不作为工具参数传入。"""

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ProcurementContext,
    ) -> ToolEnvelope[Any]: ...


class MCPClientProtocol(Protocol):
    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> Any: ...


class MCPProcurementReadGateway:
    """解析来自已绑定可信身份客户端的 MCP 响应。"""

    def __init__(
        self,
        client: MCPClientProtocol,
        *,
        bound_context: ProcurementContext,
    ) -> None:
        self._client = client
        self._bound_context = bound_context

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ProcurementContext,
    ) -> ToolEnvelope[Any]:
        if context != self._bound_context:
            return _gateway_failure(
                context.trace_id,
                "PERMISSION_DENIED",
                "Caller context does not match the authenticated MCP session",
                retryable=False,
            )
        try:
            result = await self._client.call_tool(tool_name, arguments)
            structured = getattr(result, "structured_content", None)
            if getattr(result, "is_error", True) or not isinstance(structured, dict):
                return _gateway_failure(
                    context.trace_id,
                    "INTERNAL_ERROR",
                    "MCP tool returned an invalid response",
                    retryable=True,
                )
            envelope = ToolEnvelope[Any].model_validate(structured)
            if envelope.trace_id != context.trace_id:
                return _gateway_failure(
                    context.trace_id,
                    "INTERNAL_ERROR",
                    "MCP response trace does not match the request",
                    retryable=True,
                )
            return envelope
        except TimeoutError:
            return _gateway_failure(
                context.trace_id,
                "DEPENDENCY_TIMEOUT",
                "MCP dependency timeout",
                retryable=True,
            )
        except Exception:
            return _gateway_failure(
                context.trace_id,
                "INTERNAL_ERROR",
                "MCP tool invocation failed",
                retryable=True,
            )


def _gateway_failure(
    trace_id: str,
    code: str,
    message: str,
    *,
    retryable: bool,
) -> ToolEnvelope[Any]:
    return ToolEnvelope[Any](
        ok=False,
        data=None,
        error=ToolError.model_validate(
            {"code": code, "message": message, "retryable": retryable}
        ),
        trace_id=trace_id,
    )


def _resolve_context(
    runtime: ToolRuntime[Any],
    trusted_context: ProcurementContext | None,
) -> ProcurementContext:
    runtime_context = runtime.context
    if isinstance(runtime_context, ProcurementContext):
        return runtime_context
    if trusted_context is not None:
        return trusted_context
    raise ToolException("Tool failed [PERMISSION_DENIED]: Trusted runtime context is required")


async def invoke_mcp_tool(
    gateway: ProcurementReadGateway,
    tool_name: str,
    request: BaseModel,
    runtime: ToolRuntime[ProcurementContext],
    *,
    trusted_context: ProcurementContext | None = None,
) -> str:
    context = _resolve_context(runtime, trusted_context)
    envelope = await gateway.call_tool(
        tool_name,
        {"request": request.model_dump(mode="json")},
        context,
    )
    if not envelope.ok:
        error = envelope.error
        if error is None:
            raise ToolException("Tool failed [INTERNAL_ERROR]: Invalid error response")
        retryable = str(error.retryable).lower()
        raise ToolException(
            f"Tool failed [{error.code}]: {error.message}; retryable={retryable}"
        )
    return envelope.model_dump_json()


def create_procurement_read_tools(
    gateway: ProcurementReadGateway,
    *,
    trusted_context: ProcurementContext | None = None,
) -> list[BaseTool]:
    """创建分析 Agent 可用的最小只读工具集。"""

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

    @tool("part_by_supplier")
    async def part_by_supplier_tool(
        request: PartBySupplierInput,
        runtime: ToolRuntime[ProcurementContext],
    ) -> str:
        """查询指定供应商具有有效报价的物料。"""
        return await invoke_mcp_tool(
            gateway, "part_by_supplier", request, runtime, trusted_context=trusted_context
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

    @tool("inventory_warning")
    async def inventory_warning_tool(
        request: InventoryWarningInput,
        runtime: ToolRuntime[ProcurementContext],
    ) -> str:
        """查询库存量小于或等于安全库存的物料。"""
        return await invoke_mcp_tool(
            gateway, "inventory_warning", request, runtime, trusted_context=trusted_context
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

    read_tools = [
        supplier_query_tool,
        part_query_tool,
        part_by_supplier_tool,
        quotation_query_tool,
        inventory_warning_tool,
        order_search_details_tool,
    ]
    for read_tool in read_tools:
        read_tool.handle_tool_error = True
    return read_tools
