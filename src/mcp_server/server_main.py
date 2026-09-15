"""MCP server factory with explicit dependency lifecycle."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context

from mcp_server.context import CallerContextProvider, ToolCallerContext
from mcp_server.error_mapper import error_envelope
from mcp_server.schemas import ToolEnvelope
from mcp_server.tools.inventory_tools import (
    InventorySearcher,
    InventoryWarningInput,
    inventory_warning,
)
from mcp_server.tools.order_tools import (
    OrderCancelInput,
    OrderCreateInput,
    OrderSearchDetailsInput,
    OrderSearcher,
    OrderUpdateInput,
    OrderWriteService,
    order_cancel,
    order_create,
    order_search_details,
    order_update,
)
from mcp_server.tools.parts_tools import (
    PartBySupplierInput,
    PartQueryInput,
    PartSearcher,
    part_by_supplier,
    part_query,
)
from mcp_server.tools.suppliers_tools import (
    QuotationQueryInput,
    QuotationSearcher,
    SupplierQueryInput,
    SupplierSearcher,
    quotation_query,
    supplier_query,
)
from procurepilot.config import Settings

LifecycleCallback = Callable[[], Awaitable[None]]
MCP_SERVER_INSTRUCTIONS = "提供基于证据的查询，以及受人工审批保护的订单操作。"


async def _noop() -> None:
    return None


async def _resolve_caller(
    provider: CallerContextProvider,
) -> tuple[ToolCallerContext | None, ToolEnvelope[None] | None]:
    try:
        return await provider.get_context(), None
    except Exception as error:
        return None, error_envelope(error, trace_id="context-unavailable")


@dataclass(frozen=True, slots=True)
class ServiceContainer:
    supplier_service: SupplierSearcher
    part_service: PartSearcher
    quotation_service: QuotationSearcher
    inventory_service: InventorySearcher
    order_query_service: OrderSearcher
    caller_context_provider: CallerContextProvider
    start: LifecycleCallback = _noop
    close: LifecycleCallback = _noop
    order_write_service: OrderWriteService | None = None


def create_mcp_server(settings: Settings, service_container: ServiceContainer) -> MCPServer:
    """Build a server without opening database connections at import time."""

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[ServiceContainer]:
        await service_container.start()
        try:
            yield service_container
        finally:
            await service_container.close()

    server = MCPServer(
        name="ProcurePilot",
        instructions=MCP_SERVER_INSTRUCTIONS,
        lifespan=lifespan,
    )

    @server.tool(name="supplier_query", structured_output=True)
    async def supplier_query_tool(
        request: SupplierQueryInput, context: Context[ServiceContainer, Any]
    ) -> ToolEnvelope[Any]:
        del context
        caller, failure = await _resolve_caller(service_container.caller_context_provider)
        if failure is not None:
            return failure
        assert caller is not None
        return await supplier_query(
            request,
            service=service_container.supplier_service,
            caller=caller,
            timeout_seconds=settings.request_timeout_seconds,
        )

    @server.tool(name="part_query", structured_output=True)
    async def part_query_tool(
        request: PartQueryInput, context: Context[ServiceContainer, Any]
    ) -> ToolEnvelope[Any]:
        del context
        caller, failure = await _resolve_caller(service_container.caller_context_provider)
        if failure is not None:
            return failure
        assert caller is not None
        return await part_query(
            request,
            service=service_container.part_service,
            caller=caller,
            timeout_seconds=settings.request_timeout_seconds,
        )

    @server.tool(name="part_by_supplier", structured_output=True)
    async def part_by_supplier_tool(
        request: PartBySupplierInput, context: Context[ServiceContainer, Any]
    ) -> ToolEnvelope[Any]:
        del context
        caller, failure = await _resolve_caller(service_container.caller_context_provider)
        if failure is not None:
            return failure
        assert caller is not None
        return await part_by_supplier(
            request,
            service=service_container.part_service,
            caller=caller,
            timeout_seconds=settings.request_timeout_seconds,
        )

    @server.tool(name="quotation_query", structured_output=True)
    async def quotation_query_tool(
        request: QuotationQueryInput, context: Context[ServiceContainer, Any]
    ) -> ToolEnvelope[Any]:
        del context
        caller, failure = await _resolve_caller(service_container.caller_context_provider)
        if failure is not None:
            return failure
        assert caller is not None
        return await quotation_query(
            request,
            service=service_container.quotation_service,
            caller=caller,
            timeout_seconds=settings.request_timeout_seconds,
        )

    @server.tool(name="inventory_warning", structured_output=True)
    async def inventory_warning_tool(
        request: InventoryWarningInput, context: Context[ServiceContainer, Any]
    ) -> ToolEnvelope[Any]:
        del context
        caller, failure = await _resolve_caller(service_container.caller_context_provider)
        if failure is not None:
            return failure
        assert caller is not None
        return await inventory_warning(
            request,
            service=service_container.inventory_service,
            caller=caller,
            timeout_seconds=settings.request_timeout_seconds,
        )

    @server.tool(name="order_search_details", structured_output=True)
    async def order_search_details_tool(
        request: OrderSearchDetailsInput, context: Context[ServiceContainer, Any]
    ) -> ToolEnvelope[Any]:
        del context
        caller, failure = await _resolve_caller(service_container.caller_context_provider)
        if failure is not None:
            return failure
        assert caller is not None
        return await order_search_details(
            request,
            service=service_container.order_query_service,
            caller=caller,
            timeout_seconds=settings.request_timeout_seconds,
        )

    if service_container.order_write_service is not None:

        @server.tool(name="order_create", structured_output=True)
        async def order_create_tool(
            request: OrderCreateInput, context: Context[ServiceContainer, Any]
        ) -> ToolEnvelope[Any]:
            del context
            caller, failure = await _resolve_caller(service_container.caller_context_provider)
            if failure is not None:
                return failure
            assert caller is not None
            assert service_container.order_write_service is not None
            return await order_create(
                request,
                service=service_container.order_write_service,
                caller=caller,
                timeout_seconds=settings.request_timeout_seconds,
            )

        @server.tool(name="order_update", structured_output=True)
        async def order_update_tool(
            request: OrderUpdateInput, context: Context[ServiceContainer, Any]
        ) -> ToolEnvelope[Any]:
            del context
            caller, failure = await _resolve_caller(service_container.caller_context_provider)
            if failure is not None:
                return failure
            assert caller is not None
            assert service_container.order_write_service is not None
            return await order_update(
                request,
                service=service_container.order_write_service,
                caller=caller,
                timeout_seconds=settings.request_timeout_seconds,
            )

        @server.tool(name="order_cancel", structured_output=True)
        async def order_cancel_tool(
            request: OrderCancelInput, context: Context[ServiceContainer, Any]
        ) -> ToolEnvelope[Any]:
            del context
            caller, failure = await _resolve_caller(service_container.caller_context_provider)
            if failure is not None:
                return failure
            assert caller is not None
            assert service_container.order_write_service is not None
            return await order_cancel(
                request,
                service=service_container.order_write_service,
                caller=caller,
                timeout_seconds=settings.request_timeout_seconds,
            )

    return server
