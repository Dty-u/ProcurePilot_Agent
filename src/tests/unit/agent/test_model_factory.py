import pytest

from agent.model_factory import create_chat_model
from procurepilot.config import Settings


def test_model_factory_passes_explicit_compatible_api_settings(monkeypatch) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr("agent.model_factory.ChatOpenAI", fake_chat_openai)
    settings = Settings(
        _env_file=None,
        model_name="compatible-model",
        model_base_url="https://models.example.test/v1",
        model_api_key="top-secret",
        request_timeout_seconds=12.5,
    )

    model = create_chat_model(settings)

    assert model is sentinel
    assert captured == {
        "model": "compatible-model",
        "base_url": "https://models.example.test/v1",
        "api_key": "top-secret",
        "timeout": 12.5,
    }


def test_model_factory_failure_does_not_expose_api_key(monkeypatch) -> None:
    def failing_chat_openai(**kwargs):
        raise RuntimeError(f"bad credentials: {kwargs['api_key']}")

    monkeypatch.setattr("agent.model_factory.ChatOpenAI", failing_chat_openai)
    settings = Settings(_env_file=None, model_api_key="never-log-this")

    with pytest.raises(RuntimeError) as exc_info:
        create_chat_model(settings)

    assert "never-log-this" not in str(exc_info.value)


def test_model_factory_disables_thinking_for_official_deepseek_tools(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("agent.model_factory.ChatOpenAI", fake_chat_openai)
    settings = Settings(
        _env_file=None,
        model_name="deepseek-v4-flash-vision-exp",
        model_base_url="https://api.deepseek.com",
        model_api_key="top-secret",
    )

    create_chat_model(settings)

    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}
