from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from mcp.client import Client

from mcp_server.context import ToolCallerContext
from mcp_server.server_main import ServiceContainer, create_mcp_server
from procurepilot.business.entities import InventoryItem, Part, Supplier, SupplierQuotation
from procurepilot.business.enums import Currency, PartStatus, SupplierStatus, Unit
from procurepilot.business.in_memory import InMemoryDatabase, InMemoryUnitOfWork
from procurepilot.business.services.catalog import (
    InventoryService,
    OrderQueryService,
    PartService,
    QuotationService,
    SupplierService,
)
from procurepilot.business.value_objects import Money, PositiveQuantity
from procurepilot.config import Settings

NOW = datetime(2026, 9, 8, tzinfo=UTC)


class StaticCallerProvider:
    async def get_context(self) -> ToolCallerContext:
        return ToolCallerContext(
            user_id="integration-user",
            roles=frozenset({"admin"}),
            trace_id="integration-trace",
        )


@pytest.mark.asyncio
async def test_six_tools_call_real_services_through_mcp_transport() -> None:
    database = InMemoryDatabase()
    async with InMemoryUnitOfWork(database) as uow:
        await uow.suppliers.add(Supplier("s-1", "S-1", "Alpha", SupplierStatus.ACTIVE))
        await uow.parts.add(
            Part("p-1", "P-1", "Bearing", "steel", Unit.PIECE, PartStatus.ACTIVE)
        )
        await uow.quotations.add(
            SupplierQuotation(
                "q-1",
                "s-1",
                "p-1",
                Money(Decimal("10"), Currency.CNY),
                PositiveQuantity(Decimal("1"), Unit.PIECE),
                2,
                NOW - timedelta(days=1),
                NOW + timedelta(days=1),
                "erp",
                NOW,
            )
        )
        await uow.inventory.add(
            InventoryItem(
                "i-1", "p-1", "WH-1", Unit.PIECE, Decimal("10"), Decimal("8"), Decimal("3")
            )
        )
        await uow.commit()

    def uow_factory() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(database)

    events: list[str] = []

    async def start() -> None:
        events.append("start")

    async def close() -> None:
        events.append("close")

    container = ServiceContainer(
        supplier_service=SupplierService(uow_factory),
        part_service=PartService(uow_factory),
        quotation_service=QuotationService(uow_factory),
        inventory_service=InventoryService(uow_factory),
        order_query_service=OrderQueryService(uow_factory),
        caller_context_provider=StaticCallerProvider(),
        start=start,
        close=close,
    )
    settings = Settings(
        _env_file=None,
        app_env="test",
        request_timeout_seconds=1,
        mcp_port=8101,
        fastapi_port=8100,
    )
    server = create_mcp_server(settings, container)

    expected_names = {
        "supplier_query",
        "part_query",
        "part_by_supplier",
        "quotation_query",
        "inventory_warning",
        "order_search_details",
    }
    requests = {
        "supplier_query": {},
        "part_query": {},
        "part_by_supplier": {"supplier_id": "s-1", "at": NOW.isoformat()},
        "quotation_query": {"part_id": "p-1", "at": NOW.isoformat()},
        "inventory_warning": {"part_id": "p-1"},
        "order_search_details": {},
    }
    async with Client(server) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools.tools} == expected_names
        for name, request in requests.items():
            result = await client.call_tool(name, {"request": request})
            assert result.is_error is False
            assert result.structured_content is not None
            assert result.structured_content["ok"] is True
            assert result.structured_content["trace_id"] == "integration-trace"

    assert events == ["start", "close"]
