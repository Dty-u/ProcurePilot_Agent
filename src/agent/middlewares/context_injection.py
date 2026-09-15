"""可信 Agent 运行上下文校验中间件。"""

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from agent.context import ProcurementContext


class ContextInjectionMiddleware(AgentMiddleware[Any, ProcurementContext, Any]):
    """应用未提供可信身份上下文时，在 Agent 执行前终止。"""

    def before_agent(
        self,
        state: Any,
        runtime: Runtime[ProcurementContext],
    ) -> None:
        del state
        if not isinstance(runtime.context, ProcurementContext):
            raise PermissionError("trusted ProcurementContext is required")
