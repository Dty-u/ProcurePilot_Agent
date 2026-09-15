from sqlalchemy.ext.asyncio import AsyncEngine

from procurepilot import config
from procurepilot.config import Settings
from procurepilot.infrastructure import database

TEST_DSN = "mysql+aiomysql://test_user:secret-value@127.0.0.1/procurepilot_test"


def test_database_configuration_repr_does_not_expose_password() -> None:
    settings = Settings(_env_file=None, app_env="test", mysql_dsn=TEST_DSN)
    options = database.DatabaseEngineOptions.from_settings(settings)

    assert "secret-value" not in repr(settings)
    assert "secret-value" not in repr(options)
    assert "***" in repr(options)


def test_test_database_guard_rejects_non_test_database_and_production() -> None:
    development_database = Settings(
        _env_file=None,
        app_env="development",
        mysql_dsn="mysql+aiomysql://user:password@127.0.0.1/procurepilot_dev",
    )
    production = Settings(_env_file=None, app_env="production", mysql_dsn=TEST_DSN)

    for unsafe_settings in (development_database, production):
        try:
            database.ensure_safe_test_database(unsafe_settings)
        except database.UnsafeDatabaseError:
            pass
        else:
            raise AssertionError("unsafe test database was accepted")


def test_importing_database_module_does_not_create_an_engine() -> None:
    assert not any(isinstance(value, AsyncEngine) for value in vars(database).values())


def test_engine_options_are_loaded_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        mysql_dsn=TEST_DSN,
        mysql_pool_size=7,
        mysql_max_overflow=3,
        mysql_pool_timeout_seconds=11,
        mysql_connect_timeout_seconds=9,
    )

    options = database.DatabaseEngineOptions.from_settings(settings)

    assert options.pool_size == 7
    assert options.max_overflow == 3
    assert options.pool_timeout_seconds == 11
    assert options.connect_timeout_seconds == 9


def test_settings_module_does_not_create_database_connections() -> None:
    assert not any(isinstance(value, AsyncEngine) for value in vars(config).values())
