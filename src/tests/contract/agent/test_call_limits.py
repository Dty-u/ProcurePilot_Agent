from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

from agent.middlewares import create_runtime_middleware
from agent.middlewares.context_injection import ContextInjectionMiddleware
from agent.middlewares.model_call_limit import create_model_call_limit_middleware
from agent.middlewares.tool_call_limit import create_tool_call_limit_middleware


def test_runtime_limits_are_fixed_and_fail_closed() -> None:
    middleware = create_runtime_middleware()
    model_limit = next(item for item in middleware if isinstance(item, ModelCallLimitMiddleware))
    tool_limit = next(item for item in middleware if isinstance(item, ToolCallLimitMiddleware))

    assert model_limit.run_limit == 50
    assert model_limit.exit_behavior == "error"
    assert tool_limit.run_limit == 200
    assert tool_limit.exit_behavior == "error"


def test_each_implemented_middleware_has_an_independent_factory() -> None:
    middleware = create_runtime_middleware()

    assert [type(item) for item in middleware] == [
        ContextInjectionMiddleware,
        ModelCallLimitMiddleware,
        ToolCallLimitMiddleware,
    ]
    assert isinstance(create_model_call_limit_middleware(), ModelCallLimitMiddleware)
    assert isinstance(create_tool_call_limit_middleware(), ToolCallLimitMiddleware)
