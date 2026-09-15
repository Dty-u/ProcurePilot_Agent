"""由 DeepAgents 编译且保护订单操作的子 Agent。"""

from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.subagents import CompiledSubAgent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.middlewares import create_runtime_middleware
from agent.subagents.order_prompt import ORDER_SYSTEM_PROMPT
from agent.toolsets import validate_tool_names


def create_order_subagent(
    model: BaseChatModel,
    tools: list[BaseTool],
    *,
    checkpointer: BaseCheckpointSaver[Any] | bool | None = None,
    description: str = (
        "收集并核验订单字段，请求 HITL 人工审批，然后调用受保护的订单创建、"
        "修改、取消或状态查询工具。"
    ),
    model_call_limit: int = 50,
    tool_call_limit: int = 200,
    backend: Any = StateBackend,
) -> CompiledSubAgent:
    validate_tool_names("procurement-order", tools)
    graph = create_deep_agent(
        model=model,
        tools=tools,
        subagents=[],
        system_prompt=ORDER_SYSTEM_PROMPT,
        checkpointer=checkpointer,
        store=None,
        backend=backend,
        interrupt_on={
            "order_create": {"allowed_decisions": ["approve", "reject"]},
            "order_update": {"allowed_decisions": ["approve", "reject"]},
            "order_cancel": {"allowed_decisions": ["approve", "reject"]},
        },
        middleware=create_runtime_middleware(
            model_call_limit=model_call_limit,
            tool_call_limit=tool_call_limit,
            include_context_injection=False,
        ),
        context_schema=None,
        skills=None,
        memory=None,
        response_format=None,
        debug=False,
        name="procurement-order",
        cache=None,
    )
    return CompiledSubAgent(
        name="procurement-order",
        description=description,
        runnable=graph,
    )
