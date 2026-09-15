"""真实 MCP 到主 Agent 装配的命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any, cast
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from mcp import Client

from agent.application import create_agent_application
from agent.context import ProcurementContext
from agent.main_agent import MainAgent
from agent.model_factory import create_chat_model
from agent.persistence import open_agent_persistence
from agent.tools.procurement_read import MCPClientProtocol
from mcp_server.bootstrap import create_service_container
from mcp_server.context import CallerContextProvider, ToolCallerContext
from mcp_server.server_main import create_mcp_server
from procurepilot.config import Settings


class _StaticCallerContextProvider(CallerContextProvider):
    """将一个可信 CLI 身份绑定到进程内 MCP 会话。"""

    def __init__(self, context: ProcurementContext) -> None:
        self._context = ToolCallerContext(
            user_id=context.user_id,
            roles=context.roles,
            trace_id=context.trace_id,
            thread_id=context.thread_id,
        )

    async def get_context(self) -> ToolCallerContext:
        return self._context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="通过真实 MCP Client 和持久化状态运行 ProcurePilot M8 主智能体。"
    )
    parser.add_argument("message", help="发送给主智能体的自然语言请求")
    return parser


def create_demo_context(*, trace_id: str | None = None) -> ProcurementContext:
    """创建模型无法修改的固定本地演示身份。"""

    return ProcurementContext(
        user_id="cli-demo-user",
        username="CLI Demo",
        thread_id=f"cli-{uuid4()}",
        roles=frozenset({"procurement_reader", "order_reader", "order_executor"}),
        trace_id=trace_id or f"trace-{uuid4()}",
    )


def _create_local_mcp_server(settings: Settings, context: ProcurementContext) -> Any:
    container = create_service_container(
        settings,
        _StaticCallerContextProvider(context),
    )
    return create_mcp_server(settings, container)


def _result_text(result: dict[str, Any]) -> str:
    messages = result.get("messages", [])
    if messages:
        last_message = messages[-1]
        if isinstance(last_message, BaseMessage):
            return last_message.text
    return str(result)


async def create_cli_agent(
    model: BaseChatModel,
    mcp_client: MCPClientProtocol,
    context: ProcurementContext,
    *,
    checkpointer: BaseCheckpointSaver[Any] | bool | None = None,
    store: BaseStore | None = None,
) -> MainAgent:
    """为离线契约测试暴露 CLI 的最小装配边界。"""

    return await create_agent_application(
        model,
        mcp_client,
        context,
        checkpointer=checkpointer,
        store=store,
    )


async def run_cli(message: str) -> str:
    """构建完整 M8 运行时并执行一次用户请求。"""

    settings = Settings()
    context = create_demo_context()
    model = create_chat_model(settings)
    server = _create_local_mcp_server(settings, context)
    async with Client(
        server,
        read_timeout_seconds=settings.request_timeout_seconds,
    ) as client:
        async with open_agent_persistence(settings) as persistence:
            await persistence.threads.claim(context)
            main_agent = await create_cli_agent(
                model,
                cast(MCPClientProtocol, client),
                context,
                checkpointer=persistence.checkpointer,
                store=persistence.store,
            )
            result = await main_agent.graph.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"thread_id": context.thread_id}},
                context=context,
            )
    return _result_text(result)


def main() -> None:
    args = build_parser().parse_args()
    print(asyncio.run(run_cli(args.message)))


if __name__ == "__main__":
    main()
