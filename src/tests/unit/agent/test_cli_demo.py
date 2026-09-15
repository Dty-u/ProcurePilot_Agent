from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent.cli_demo import build_parser, create_cli_agent, create_demo_context


class ToolModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "cli-tool-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ToolModel:
        return self

    def _generate(self, messages: Any, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])


class Client:
    async def call_tool(self, name, arguments):
        raise AssertionError("minimal assembly must not invoke a tool")


def test_cli_accepts_free_form_user_message() -> None:
    parser = build_parser()
    args = parser.parse_args(["比较物料 part-001 的报价"])

    assert args.message == "比较物料 part-001 的报价"


def test_demo_context_uses_fixed_trusted_roles() -> None:
    context = create_demo_context(trace_id="trace-cli-demo")

    assert context.user_id == "cli-demo-user"
    assert context.roles == frozenset(
        {"procurement_reader", "order_reader", "order_executor"}
    )
    assert context.trace_id == "trace-cli-demo"
    assert "--roles" not in build_parser().format_help()


@pytest.mark.asyncio
async def test_cli_completes_minimal_real_agent_assembly() -> None:
    agent = await create_cli_agent(
        ToolModel(),
        Client(),
        create_demo_context(trace_id="trace-cli-assembly"),
    )

    assert agent.framework == "deepagents"
    assert len(agent.subagent_tool_names["procurement-order"]) == 8
