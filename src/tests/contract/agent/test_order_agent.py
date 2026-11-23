from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from langgraph.types import Command

from agent.context import ProcurementContext
from agent.main_agent import create_main_agent
from agent.persistence import open_agent_persistence
from agent.subagents.order_prompt import ORDER_SYSTEM_PROMPT
from agent.subagents.procurement_order import create_order_subagent
from agent.tools.procurement_order import create_procurement_order_tools
from agent.toolsets import ANALYST_TOOL_NAMES, ORDER_TOOL_NAMES
from mcp_server.schemas import ToolEnvelope
from procurepilot.config import Settings


class ToolModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "tool-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ToolModel":
        return self

    def _generate(self, messages: Any, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])


class OrderWriteModel(ToolModel):
    tool_name: str
    tool_request: dict[str, Any]

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": self.tool_name,
                                "args": {"request": self.tool_request},
                                "id": f"call-{self.tool_name}",
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )


class ResumableOrderWriteModel(OrderWriteModel):
    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        from langchain_core.messages import ToolMessage

        if any(isinstance(message, ToolMessage) for message in messages):
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="订单操作已完成"))]
            )
        return super()._generate(messages, stop, run_manager, **kwargs)


def named_tools(names: frozenset[str]) -> list[StructuredTool]:
    def placeholder() -> str:
        """测试占位。"""
        return "ok"

    return [
        StructuredTool.from_function(
            placeholder,
            name=name,
            description=f"{name} test tool",
        )
        for name in sorted(names)
    ]


def test_order_subagent_has_fixed_safety_flow_and_only_order_tools() -> None:
    spec = create_order_subagent(ToolModel(), named_tools(ORDER_TOOL_NAMES))

    assert spec["name"] == "procurement-order"
    assert spec["runnable"] is not None
    assert "不得猜测" in ORDER_SYSTEM_PROMPT
    assert "已经批准" in ORDER_SYSTEM_PROMPT
    assert "自动重试" in ORDER_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_main_agent_compiles_with_explicit_separate_toolsets() -> None:
    agent = await create_main_agent(
        ToolModel(),
        named_tools(ANALYST_TOOL_NAMES),
        named_tools(ORDER_TOOL_NAMES),
    )

    assert agent.main_tool_names == ()
    assert agent.framework == "deepagents"
    assert agent.subagent_frameworks == {
        "procurement-analyst": "deepagents",
        "procurement-order": "deepagents",
    }
    assert set(agent.subagent_tool_names["procurement-analyst"]) == ANALYST_TOOL_NAMES
    assert set(agent.subagent_tool_names["procurement-order"]) == ORDER_TOOL_NAMES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "tool_request"),
    [
        (
            "order_create",
            {
                "operation_id": "operation-1",
                "approval_id": "approval-1",
                "idempotency_key": "idem-1",
            },
        ),
        (
            "order_update",
            {
                "operation_id": "operation-1",
                "approval_id": "approval-1",
                "idempotency_key": "idem-1",
                "expected_version": 2,
            },
        ),
        (
            "order_cancel",
            {
                "operation_id": "operation-1",
                "approval_id": "approval-1",
                "idempotency_key": "idem-1",
                "expected_version": 2,
            },
        ),
    ],
)
async def test_order_write_interrupts_before_mcp_gateway_is_called(
    tool_name: str,
    tool_request: dict[str, Any],
) -> None:
    class Gateway:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def call_tool(self, tool_name, arguments, context):
            self.calls.append(tool_name)
            return ToolEnvelope(
                ok=True,
                data={"unexpected": True},
                error=None,
                trace_id=context.trace_id,
            )

    context = ProcurementContext(
        user_id="user-1",
        roles=frozenset({"procurement_reader", "order_reader", "order_executor"}),
        thread_id="thread-hitl-1",
        trace_id="trace-hitl-1",
    )
    gateway = Gateway()
    spec = create_order_subagent(
        OrderWriteModel(tool_name=tool_name, tool_request=tool_request),
        create_procurement_order_tools(gateway, trusted_context=context),
    )

    result = await spec["runnable"].ainvoke(
        {"messages": [HumanMessage(content="创建已批准订单")]},
        config={"configurable": {"thread_id": context.thread_id}},
        context=context,
    )

    assert result["__interrupt__"]
    hitl_request = result["__interrupt__"][0].value
    assert hitl_request["review_configs"][0]["allowed_decisions"] == [
        "approve",
        "reject",
    ]
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_order_interrupt_resumes_after_agent_recreation_with_shared_checkpoint() -> None:
    settings = Settings(_env_file=None)
    context = ProcurementContext(
        user_id="user-1",
        roles=frozenset({"procurement_reader", "order_reader", "order_executor"}),
        thread_id="thread-resume-order",
        trace_id="trace-resume-order",
    )
    config = {"configurable": {"thread_id": context.thread_id}}

    class Gateway:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def call_tool(self, tool_name, arguments, tool_context):
            self.calls.append(tool_name)
            return ToolEnvelope(
                ok=True,
                data={"order_id": "order-1"},
                error=None,
                trace_id=tool_context.trace_id,
            )

    gateway = Gateway()
    model = ResumableOrderWriteModel(
        tool_name="order_create",
        tool_request={
            "operation_id": "operation-1",
            "approval_id": "approval-1",
            "idempotency_key": "idem-1",
        },
    )
    tools = create_procurement_order_tools(gateway, trusted_context=context)

    async with open_agent_persistence(settings, in_memory=True) as persistence:
        first_spec = create_order_subagent(
            model,
            tools,
            checkpointer=persistence.checkpointer,
        )
        interrupted = await first_spec["runnable"].ainvoke(
            {"messages": [HumanMessage(content="创建订单")]},
            config=config,
            context=context,
        )
        assert interrupted["__interrupt__"]

        recreated_spec = create_order_subagent(
            model,
            tools,
            checkpointer=persistence.checkpointer,
        )
        completed = await recreated_spec["runnable"].ainvoke(
            Command(resume={"decisions": [{"type": "approve"}]}),
            config=config,
            context=context,
        )

    assert completed["messages"][-1].text == "订单操作已完成"
    assert gateway.calls == ["order_create"]
