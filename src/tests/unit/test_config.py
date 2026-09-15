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


def test_limits_and_mysql_agent_storage_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.request_timeout_seconds > 0
    assert settings.model_call_limit == 50
    assert settings.tool_call_limit == 200
    assert settings.agent_checkpoint_mysql_dsn is None
    assert settings.agent_checkpoint_auto_setup is False
    assert "agent_store_path" not in Settings.model_fields
    assert "agent_resume_path" not in Settings.model_fields
    assert "display_history_path" not in Settings.model_fields


def test_runtime_configuration_and_dependencies_do_not_reference_sqlite() -> None:
    project_root = Path(__file__).parents[3]

    env_template = (project_root / ".env.example").read_text(encoding="utf-8")
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")

    assert "SQLITE" not in env_template.upper()
    assert "aiosqlite" not in pyproject
    assert "langgraph-checkpoint-sqlite" not in pyproject


def test_checkpoint_mysql_dsn_is_required_only_when_persistence_opens() -> None:
    settings = Settings(_env_file=None)

    with pytest.raises(ValueError, match="AGENT_CHECKPOINT_MYSQL_DSN is required"):
        settings.require_checkpoint_mysql_dsn()


def test_test_environment_rejects_non_test_checkpoint_database() -> None:
    with pytest.raises(ValueError, match="checkpoint database containing 'test'"):
        Settings(
            _env_file=None,
            app_env="test",
            agent_checkpoint_mysql_dsn=(
                "mysql+aiomysql://checkpoint:secret@localhost/procurepilot_checkpoint"
            ),
        )


def test_checkpoint_database_must_be_separate_from_business_database() -> None:
    with pytest.raises(ValueError, match="must use a database separate"):
        Settings(
            _env_file=None,
            mysql_dsn="mysql+aiomysql://business:secret@localhost/procurepilot_dev",
            agent_checkpoint_mysql_dsn=(
                "mysql+aiomysql://checkpoint:other-secret@localhost/procurepilot_dev"
            ),
        )


def test_checkpoint_database_detects_equivalent_loopback_hosts() -> None:
    with pytest.raises(ValueError, match="must use a database separate"):
        Settings(
            _env_file=None,
            mysql_dsn="mysql+aiomysql://business:secret@localhost/procurepilot_dev",
            agent_checkpoint_mysql_dsn=(
                "mysql+aiomysql://checkpoint:other-secret@127.0.0.1/procurepilot_dev"
            ),
        )


def test_checkpoint_dsn_rejects_non_mysql_scheme_without_exposing_secret() -> None:
    with pytest.raises(ValueError) as exc_info:
        Settings(
            _env_file=None,
            agent_checkpoint_mysql_dsn="postgresql://checkpoint:very-secret@localhost/state",
        )

    assert "must use mysql" in str(exc_info.value)
    assert "very-secret" not in str(exc_info.value)


def test_request_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, request_timeout_seconds=0)


def test_mcp_and_fastapi_ports_must_differ_for_network_transport() -> None:
    with pytest.raises(ValueError, match="MCP_PORT must differ"):
        Settings(
            _env_file=None,
            mcp_transport="streamable-http",
            mcp_port=8000,
            fastapi_port=8000,
        )


def test_stdio_transport_does_not_require_a_distinct_port() -> None:
    settings = Settings(
        _env_file=None,
        mcp_transport="stdio",
        mcp_port=8000,
        fastapi_port=8000,
    )

    assert settings.mcp_transport == "stdio"


def test_test_environment_accepts_test_database() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        mysql_dsn="mysql+aiomysql://buyer:secret@localhost/procurepilot_test",
    )

    assert settings.mysql_dsn is not None
