"""显式构造已配置的 OpenAI 兼容聊天模型。"""

from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from procurepilot.config import Settings


def create_chat_model(settings: Settings) -> BaseChatModel:
    """仅在应用启动时显式调用才创建真实模型。"""

    try:
        runtime = settings.require_model_config()
        model_options: dict[str, Any] = {
            "model": runtime.model_name,
            "base_url": str(runtime.model_base_url),
            "api_key": cast(Any, runtime.model_api_key.get_secret_value()),
            "timeout": settings.request_timeout_seconds,
        }
        model_host = runtime.model_base_url.host
        if model_host is not None and model_host.casefold() == "api.deepseek.com":
            model_options["extra_body"] = {"thinking": {"type": "disabled"}}
        return ChatOpenAI(**model_options)
    except Exception:
        raise RuntimeError("Failed to initialize configured chat model") from None
