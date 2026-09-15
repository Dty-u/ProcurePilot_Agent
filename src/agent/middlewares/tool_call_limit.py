"""工具调用次数限制中间件工厂。"""

from langchain.agents.middleware import ToolCallLimitMiddleware

DEFAULT_TOOL_CALL_LIMIT = 200


def create_tool_call_limit_middleware(
    run_limit: int = DEFAULT_TOOL_CALL_LIMIT,
) -> ToolCallLimitMiddleware:
    """创建达到调用上限后直接报错的工具调用限制。"""

    return ToolCallLimitMiddleware(run_limit=run_limit, exit_behavior="error")
