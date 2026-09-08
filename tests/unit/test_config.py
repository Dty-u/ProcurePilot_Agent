from pathlib import Path

import pytest

from procurepilot.config import Settings


def test_settings_can_be_created_without_model_api_key() -> None:
    settings = Settings(_env_file=None)

    assert settings.model_api_key is None


def test_model_config_requires_api_key_only_when_requested() -> None:
    settings = Settings(_env_file=None)

    with pytest.raises(ValueError, match="MODEL_API_KEY is required"):
        settings.require_model_config()


def test_model_config_exposes_validated_runtime_values() -> None:
    settings = Settings(
        _env_file=None,
        model_name="test-model",
        model_base_url="https://models.example.test/v1",
        model_api_key="model-secret",
    )

    model_config = settings.require_model_config()

    assert model_config.model_name == "test-model"
    assert str(model_config.model_base_url) == "https://models.example.test/v1"
    assert model_config.model_api_key.get_secret_value() == "model-secret"


def test_settings_repr_masks_api_key_and_mysql_password() -> None:
    settings = Settings(
        _env_file=None,
        model_api_key="model-secret",
        mysql_dsn="mysql+aiomysql://buyer:mysql-secret@localhost/procurepilot_dev",
    )

    rendered = repr(settings)

    assert "model-secret" not in rendered
    assert "mysql-secret" not in rendered
    assert "**********" in rendered


def test_validation_error_does_not_expose_secrets() -> None:
    with pytest.raises(ValueError) as exc_info:
        Settings(
            _env_file=None,
            app_env="test",
            model_api_key="model-secret",
            mysql_dsn="mysql+aiomysql://buyer:mysql-secret@localhost/procurepilot",
        )

    rendered = str(exc_info.value)
    assert "model-secret" not in rendered
    assert "mysql-secret" not in rendered


def test_limits_and_paths_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.request_timeout_seconds > 0
    assert settings.model_call_limit == 50
    assert settings.tool_call_limit == 200
    assert settings.agent_checkpoint_path == Path("data/agent_checkpoints.sqlite3")
    assert settings.agent_store_path == Path("data/agent_store.sqlite3")
    assert settings.display_history_path == Path("data/display_history.sqlite3")


def test_request_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, request_timeout_seconds=0)


def test_test_environment_accepts_test_database() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        mysql_dsn="mysql+aiomysql://buyer:secret@localhost/procurepilot_test",
    )

    assert settings.mysql_dsn is not None
