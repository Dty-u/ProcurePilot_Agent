from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent.application import create_agent_application
from agent.context import ProcurementContext
from agent.persistence import open_agent_persistence
from agent.toolsets import ANALYST_TOOL_NAMES, ORDER_TOOL_NAMES
from procurepilot.config import Settings


class ToolModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "assembly-tool-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ToolModel:
        return self

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])


class Client:
    async def call_tool(self, name, arguments):
        raise AssertionError("assembly must not call MCP before an Agent tool is selected")


@pytest.mark.asyncio
async def test_real_application_assembly_builds_both_mcp_toolsets() -> None:
    context = ProcurementContext(
        user_id="user-1",
        roles=frozenset({"procurement_reader", "order_reader", "order_executor"}),
        thread_id="thread-1",
        trace_id="trace-1",
    )

    agent = await create_agent_application(ToolModel(), Client(), context)

    assert agent.main_tool_names == ()
    assert set(agent.subagent_tool_names["procurement-analyst"]) == ANALYST_TOOL_NAMES
    assert set(agent.subagent_tool_names["procurement-order"]) == ORDER_TOOL_NAMES


@pytest.mark.asyncio
async def test_application_assembly_uses_injected_checkpointer_and_store() -> None:
    settings = Settings(_env_file=None)
    context = ProcurementContext(
        user_id="user-1",
        roles=frozenset({"procurement_reader"}),
        thread_id="thread-persisted",
        trace_id="trace-persisted",
    )
    config = {"configurable": {"thread_id": context.thread_id}}

    async with open_agent_persistence(settings, in_memory=True) as persistence:
        await persistence.threads.claim(context)
        agent = await create_agent_application(
            ToolModel(),
            Client(),
            context,
            checkpointer=persistence.checkpointer,
            store=persistence.store,
        )
        await agent.graph.ainvoke(
            {"messages": [HumanMessage(content="你好")]},
            config=config,
            context=context,
        )

        assert await persistence.checkpointer.aget_tuple(config) is not None
