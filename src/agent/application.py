"""从 MCP Client 创建受限主 Agent 的 M7/M8 应用装配。"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from agent.context import ProcurementContext
from agent.main_agent import MainAgent, create_main_agent
from agent.tools.procurement_order import (
    MCPProcurementOrderGateway,
    create_procurement_order_tools,
)
from agent.tools.procurement_read import (
    MCPClientProtocol,
    MCPProcurementReadGateway,
    create_procurement_read_tools,
)


async def create_agent_application(
    model: BaseChatModel,
    mcp_client: MCPClientProtocol,
    context: ProcurementContext,
    *,
    checkpointer: BaseCheckpointSaver[Any] | bool | None = None,
    store: BaseStore | None = None,
    backend: Any = None,
    skills: list[str] | None = None,
) -> MainAgent:
    """绑定一次可信身份，创建两套 MCP 工具并编译主 Agent。"""

    analyst_gateway = MCPProcurementReadGateway(mcp_client, bound_context=context)
    order_gateway = MCPProcurementOrderGateway(mcp_client, bound_context=context)
    analyst_tools = create_procurement_read_tools(
        analyst_gateway,
        trusted_context=context,
    )
    order_tools = create_procurement_order_tools(
        order_gateway,
        trusted_context=context,
    )
    options: dict[str, Any] = {
        "checkpointer": checkpointer,
        "store": store,
        "skills": skills,
    }
    if backend is not None:
        options["backend"] = backend
    return await create_main_agent(
        model,
        analyst_tools,
        order_tools,
        **options,
    )
