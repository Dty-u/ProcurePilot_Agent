"""显式构造 MySQL 引擎，并带有测试库安全防护。"""

from dataclasses import dataclass

from pydantic import SecretStr
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from procurepilot.config import Settings


class UnsafeDatabaseError(RuntimeError):
    """数据库操作可能影响非测试数据库。"""


@dataclass(frozen=True, slots=True)
class DatabaseEngineOptions:
    dsn: SecretStr
    pool_size: int
    max_overflow: int
    pool_timeout_seconds: float
    connect_timeout_seconds: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "DatabaseEngineOptions":
        if settings.mysql_dsn is None:
            raise ValueError("MYSQL_DSN is required to initialize the database")
        return cls(
            dsn=settings.mysql_dsn,
            pool_size=settings.mysql_pool_size,
            max_overflow=settings.mysql_max_overflow,
            pool_timeout_seconds=settings.mysql_pool_timeout_seconds,
            connect_timeout_seconds=settings.mysql_connect_timeout_seconds,
        )

    def sqlalchemy_url(self) -> URL:
        return make_url(self.dsn.get_secret_value())


def ensure_safe_test_database(settings: Settings) -> None:
    """除非配置指向专用测试库，否则一律拒绝执行。"""
    if settings.app_env != "test" or settings.mysql_dsn is None:
        raise UnsafeDatabaseError("database tests require APP_ENV=test and MYSQL_DSN")
    database_name = make_url(settings.mysql_dsn.get_secret_value()).database
    if database_name is None or "test" not in database_name.casefold():
        raise UnsafeDatabaseError("database tests require a database name containing 'test'")


def create_database_engine(
    settings: Settings,
    *,
    require_test_database: bool = False,
) -> AsyncEngine:
    """创建引擎，首次使用前不打开连接。"""
    if require_test_database:
        ensure_safe_test_database(settings)
    options = DatabaseEngineOptions.from_settings(settings)
    return create_async_engine(
        options.sqlalchemy_url(),
        pool_pre_ping=True,
        pool_size=options.pool_size,
        max_overflow=options.max_overflow,
        pool_timeout=options.pool_timeout_seconds,
        connect_args={"connect_timeout": options.connect_timeout_seconds},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """创建 UoW 作用域的会话，提交时不使已返回的领域结果过期。"""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
