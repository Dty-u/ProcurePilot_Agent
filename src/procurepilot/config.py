"""Application settings loaded without performing external I/O."""

from typing import Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelRuntimeConfig(BaseModel):
    """Validated values required to initialize a real chat model."""

    model_config = ConfigDict(frozen=True)

    model_name: str
    model_base_url: HttpUrl
    model_api_key: SecretStr


class Settings(BaseSettings):
    """Central application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    model_name: str = "gpt-4.1-mini"
    model_base_url: HttpUrl = HttpUrl("https://api.openai.com/v1")
    model_api_key: SecretStr | None = None

    mysql_dsn: SecretStr | None = None
    mysql_pool_size: PositiveInt = 5
    mysql_max_overflow: int = Field(default=10, ge=0)
    mysql_pool_timeout_seconds: float = Field(default=30.0, gt=0)
    mysql_connect_timeout_seconds: PositiveInt = 10

    agent_checkpoint_mysql_dsn: SecretStr | None = None
    agent_checkpoint_auto_setup: bool = False

    mcp_server_url: HttpUrl = HttpUrl("http://127.0.0.1:8001/mcp")
    mcp_transport: Literal["stdio", "sse", "streamable-http"] = "streamable-http"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8001, ge=1, le=65535)
    fastapi_port: int = Field(default=18000, ge=1, le=65535)
    opensandbox_base_url: HttpUrl = HttpUrl("http://127.0.0.1:8080")
    opensandbox_api_key: SecretStr | None = None
    opensandbox_image: str | None = None
    opensandbox_cpu: str = "500m"
    opensandbox_memory: str = "512Mi"
    opensandbox_disk: str = "1Gi"
    opensandbox_max_file_bytes: PositiveInt = 10_000_000
    opensandbox_max_processes: PositiveInt = 32
    opensandbox_ttl_seconds: PositiveInt = 600
    opensandbox_ready_timeout_seconds: PositiveInt = 30

    request_timeout_seconds: float = Field(default=30.0, gt=0)
    model_call_limit: PositiveInt = 50
    tool_call_limit: PositiveInt = 200

    def __init__(self, **values: Any) -> None:
        super().__init__(**values)
        self._validate_test_database()
        self._validate_checkpoint_database()
        if self.mcp_transport != "stdio" and self.mcp_port == self.fastapi_port:
            raise ValueError("MCP_PORT must differ from FASTAPI_PORT")

    def require_model_config(self) -> ModelRuntimeConfig:
        """Return model settings only when credentials are explicitly required."""
        if self.model_api_key is None:
            raise ValueError("MODEL_API_KEY is required to initialize a real model")

        return ModelRuntimeConfig(
            model_name=self.model_name,
            model_base_url=self.model_base_url,
            model_api_key=self.model_api_key,
        )

    def require_checkpoint_mysql_dsn(self) -> SecretStr:
        """仅在打开持久化 Checkpoint 时要求独立 MySQL DSN。"""

        if self.agent_checkpoint_mysql_dsn is None:
            raise ValueError("AGENT_CHECKPOINT_MYSQL_DSN is required")
        return self.agent_checkpoint_mysql_dsn

    def _validate_test_database(self) -> Self:
        if self.app_env != "test" or self.mysql_dsn is None:
            return self

        database_name = urlsplit(self.mysql_dsn.get_secret_value()).path.strip("/").lower()
        if "test" not in database_name:
            raise ValueError("Test environment requires a MySQL database containing 'test'")
        return self

    def _validate_checkpoint_database(self) -> Self:
        if self.agent_checkpoint_mysql_dsn is None:
            return self

        checkpoint_target = _mysql_target(
            self.agent_checkpoint_mysql_dsn,
            setting_name="AGENT_CHECKPOINT_MYSQL_DSN",
        )
        if self.app_env == "test" and "test" not in checkpoint_target[2]:
            raise ValueError(
                "Test environment requires a checkpoint database containing 'test'"
            )
        if self.mysql_dsn is not None:
            business_target = _mysql_target(self.mysql_dsn, setting_name="MYSQL_DSN")
            if checkpoint_target == business_target:
                raise ValueError(
                    "Agent checkpoint must use a database separate from business MySQL"
                )
        return self


def _mysql_target(dsn: SecretStr, *, setting_name: str) -> tuple[str, int, str]:
    """提取不含凭据的 MySQL 目标，用于安全校验数据库隔离。"""

    parsed = urlsplit(dsn.get_secret_value())
    if parsed.scheme not in {"mysql", "mysql+aiomysql"}:
        raise ValueError(f"{setting_name} must use mysql or mysql+aiomysql")
    database_name = parsed.path.strip("/").lower()
    if parsed.hostname is None or not database_name:
        raise ValueError(f"{setting_name} must include host and database")
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        hostname = "loopback"
    return hostname, parsed.port or 3306, database_name
