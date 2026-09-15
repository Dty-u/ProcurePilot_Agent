"""DeepAgents 协调器装配及确定性路由契约。"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.subagents import CompiledSubAgent, SubAgent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from agent.context import ProcurementContext
from agent.middlewares import create_runtime_middleware
from agent.prompts import MAIN_SYSTEM_PROMPT
from agent.subagents.loader import load_subagent_configs, resolve_subagent_tools
from agent.subagents.procurement_analyst import create_analyst_agent
from agent.subagents.procurement_order import create_order_subagent
from agent.toolsets import MAIN_TOOL_NAMES, validate_tool_names


class RouteTarget(StrEnum):
    MAIN = "main"
    ANALYST = "procurement-analyst"
    ORDER = "procurement-order"


@dataclass(frozen=True, slots=True)
class RouteDecision:
    target: RouteTarget
    requires_write_confirmation: bool = False


_ANALYSIS_TERMS = ("分析", "比较", "对比", "报告", "建议", "评估", "行情", "比价", "筛选")
_WRITE_TERMS = ("下单", "创建订单", "修改订单", "更新订单", "取消订单")
_ORDER_TERMS = (*_WRITE_TERMS, "订单状态", "查询订单", "采购订单")


def route_request(text: str) -> RouteDecision:
    normalized = text.casefold()
    has_analysis = any(term in normalized for term in _ANALYSIS_TERMS)
    has_write = any(term in normalized for term in _WRITE_TERMS)
    if has_analysis and has_write:
        return RouteDecision(RouteTarget.ANALYST, requires_write_confirmation=True)
    if has_analysis:
        return RouteDecision(RouteTarget.ANALYST)
    if any(term in normalized for term in _ORDER_TERMS):
        return RouteDecision(RouteTarget.ORDER)
    return RouteDecision(RouteTarget.MAIN)


class MainAgent:
    def __init__(self, graph: Any, subagent_tool_names: dict[str, tuple[str, ...]]) -> None:
        self.graph = graph
        self.framework = "deepagents"
        self.main_tool_names = tuple(sorted(MAIN_TOOL_NAMES))
        self.subagent_tool_names = subagent_tool_names
        self.subagent_frameworks = {
            name: "deepagents" for name in subagent_tool_names
        }


async def create_main_agent(
    model: BaseChatModel,
    analyst_tools: list[BaseTool],
    order_tools: list[BaseTool],
    *,
    checkpointer: BaseCheckpointSaver[Any] | bool | None = None,
    store: BaseStore | None = None,
    backend: Any = StateBackend,
    skills: list[str] | None = None,
    interrupt_on: dict[str, bool | dict[str, Any]] | None = None,
    middleware: list[AgentMiddleware[Any, Any, Any]] | None = None,
) -> MainAgent:
    configs = load_subagent_configs()
    analyst_config = configs["procurement-analyst"]
    order_config = configs["procurement-order"]
    resolved_analyst_tools = resolve_subagent_tools(analyst_config, analyst_tools)
    resolved_order_tools = resolve_subagent_tools(order_config, order_tools)
    analyst_names = validate_tool_names("procurement-analyst", resolved_analyst_tools)
    order_names = validate_tool_names("procurement-order", resolved_order_tools)
    validate_tool_names("main", [])

    analyst = await create_analyst_agent(
        model,
        resolved_analyst_tools,
        model_call_limit=analyst_config.model_call_limit,
        tool_call_limit=analyst_config.tool_call_limit,
        backend=backend,
        skills=skills,
    )
    analyst_spec = CompiledSubAgent(
        name=analyst_config.name,
        description=analyst_config.description,
        runnable=analyst.graph,
    )
    order_spec = create_order_subagent(
        model,
        resolved_order_tools,
        checkpointer=checkpointer,
        description=order_config.description,
        model_call_limit=order_config.model_call_limit,
        tool_call_limit=order_config.tool_call_limit,
        backend=backend,
    )
    configured_middleware = middleware or create_runtime_middleware()
    write_interrupts: dict[str, bool | dict[str, Any]] = interrupt_on or {}
    subagents: list[SubAgent | CompiledSubAgent] = [analyst_spec, order_spec]
    graph = create_deep_agent(
        model=model,
        tools=[],
        subagents=subagents,
        system_prompt=MAIN_SYSTEM_PROMPT,
        checkpointer=checkpointer,
        store=store,
        backend=backend,
        interrupt_on=cast(Any, write_interrupts),
        middleware=configured_middleware,
        context_schema=ProcurementContext,
        skills=skills,
        memory=None,
        response_format=None,
        debug=False,
        name="procurepilot-main",
        cache=None,
    )
    return MainAgent(
        graph,
        {
            "procurement-analyst": analyst_names,
            "procurement-order": order_names,
        },
    )
