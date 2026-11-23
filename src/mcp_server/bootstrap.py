"""基于 MySQL 的 MCP 服务容器的组合根。"""

from typing import cast

from mcp_server.context import CallerContextProvider
from mcp_server.server_main import ServiceContainer
from procurepilot.business.repositories import UnitOfWork
from procurepilot.business.services.catalog import (
    InventoryService,
    OrderQueryService,
    PartService,
    QuotationService,
    SupplierService,
)
from procurepilot.business.services.order import OrderService
from procurepilot.config import Settings
from procurepilot.infrastructure.database import create_database_engine, create_session_factory
from procurepilot.infrastructure.mysql_uow import MySQLUnitOfWork


def create_service_container(
    settings: Settings,
    caller_context_provider: CallerContextProvider,
) -> ServiceContainer:
    """构建具体的 MCP 依赖，直到工具被调用时才建立连接。"""

    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    def uow_factory() -> UnitOfWork:
        return cast(UnitOfWork, MySQLUnitOfWork(session_factory))

    return ServiceContainer(
        supplier_service=SupplierService(uow_factory),
        part_service=PartService(uow_factory),
        quotation_service=QuotationService(uow_factory),
        inventory_service=InventoryService(uow_factory),
        order_query_service=OrderQueryService(uow_factory),
        caller_context_provider=caller_context_provider,
        close=engine.dispose,
        order_write_service=OrderService(uow_factory),
    )
