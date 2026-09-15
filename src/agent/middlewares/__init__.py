"""按固定顺序装配当前已经实现的 Agent 中间件。"""

from typing import Any

from langchain.agents.middleware import AgentMiddleware

from agent.middlewares.context_injection import ContextInjectionMiddleware
from agent.middlewares.model_call_limit import (
    DEFAULT_MODEL_CALL_LIMIT,
    create_model_call_limit_middleware,
)
from agent.middlewares.tool_call_limit import (
    DEFAULT_TOOL_CALL_LIMIT,
    create_tool_call_limit_middleware,
)

__all__ = [
    "ContextInjectionMiddleware",
    "create_model_call_limit_middleware",
    "create_runtime_middleware",
    "create_tool_call_limit_middleware",
]


def create_runtime_middleware(
    *,
    model_call_limit: int = DEFAULT_MODEL_CALL_LIMIT,
    tool_call_limit: int = DEFAULT_TOOL_CALL_LIMIT,
    include_context_injection: bool = True,
) -> list[AgentMiddleware[Any, Any, Any]]:
    """按照上下文、模型上限、工具上限的顺序创建中间件栈。"""

    middleware: list[AgentMiddleware[Any, Any, Any]] = []
    if include_context_injection:
        middleware.append(ContextInjectionMiddleware())
    middleware.extend(
        [
            create_model_call_limit_middleware(model_call_limit),
            create_tool_call_limit_middleware(tool_call_limit),
        ]
    )
    return middleware
