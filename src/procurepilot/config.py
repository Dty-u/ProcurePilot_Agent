"""Application settings loaded without performing external I/O."""

from pathlib import Path
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

    agent_checkpoint_path: Path = Path("data/agent_checkpoints.sqlite3")
    agent_store_path: Path = Path("data/agent_store.sqlite3")
    display_history_path: Path = Path("data/display_history.sqlite3")

    mcp_server_url: HttpUrl = HttpUrl("http://127.0.0.1:8001/mcp")
    opensandbox_base_url: HttpUrl = HttpUrl("http://127.0.0.1:8080")
    opensandbox_api_key: SecretStr | None = None

    request_timeout_seconds: float = Field(default=30.0, gt=0)
    model_call_limit: PositiveInt = 50
    tool_call_limit: PositiveInt = 200

    def __init__(self, **values: Any) -> None:
        super().__init__(**values)
        self._validate_test_database()

    def require_model_config(self) -> ModelRuntimeConfig:
        """Return model settings only when credentials are explicitly required."""
        if self.model_api_key is None:
            raise ValueError("MODEL_API_KEY is required to initialize a real model")

        return ModelRuntimeConfig(
            model_name=self.model_name,
            model_base_url=self.model_base_url,
            model_api_key=self.model_api_key,
        )

    def _validate_test_database(self) -> Self:
        if self.app_env != "test" or self.mysql_dsn is None:
            return self

        database_name = urlsplit(self.mysql_dsn.get_secret_value()).path.strip("/").lower()
        if "test" not in database_name:
            raise ValueError("Test environment requires a MySQL database containing 'test'")
        return self
