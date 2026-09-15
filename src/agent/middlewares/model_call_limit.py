"""模型调用次数限制中间件工厂。"""

from langchain.agents.middleware import ModelCallLimitMiddleware

DEFAULT_MODEL_CALL_LIMIT = 50


def create_model_call_limit_middleware(
    run_limit: int = DEFAULT_MODEL_CALL_LIMIT,
) -> ModelCallLimitMiddleware:
    """创建达到调用上限后直接报错的模型调用限制。"""

    return ModelCallLimitMiddleware(run_limit=run_limit, exit_behavior="error")
