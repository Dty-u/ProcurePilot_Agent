from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from procurepilot.config import Settings
from procurepilot.infrastructure.database import (
    UnsafeDatabaseError,
    create_database_engine,
    create_session_factory,
    ensure_safe_test_database,
)
from procurepilot.infrastructure.orm_models import Base


@pytest.fixture(scope="session")
def mysql_test_settings() -> Settings:
    settings = Settings()
    if settings.mysql_dsn is None:
        pytest.skip("MYSQL_DSN is not configured; MySQL integration tests were not run")
    try:
        ensure_safe_test_database(settings)
    except UnsafeDatabaseError as exc:
        pytest.skip(f"未配置安全 MySQL 测试库：{exc}")
    return settings


@pytest.fixture(scope="session")
def alembic_config(mysql_test_settings: Settings) -> Iterator[Config]:
    assert mysql_test_settings.mysql_dsn is not None
    configuration = Config("alembic.ini")
    dsn = mysql_test_settings.mysql_dsn.get_secret_value().replace("%", "%%")
    configuration.set_main_option("sqlalchemy.url", dsn)
    yield configuration


@pytest.fixture(scope="session")
def migrated_mysql_database(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")


@pytest_asyncio.fixture
async def mysql_engine(
    mysql_test_settings: Settings,
    migrated_mysql_database: None,
) -> AsyncIterator[AsyncEngine]:
    engine = create_database_engine(mysql_test_settings, require_test_database=True)
    try:
        async with engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                await connection.execute(table.delete())
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def mysql_session_factory(
    mysql_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(mysql_engine)
