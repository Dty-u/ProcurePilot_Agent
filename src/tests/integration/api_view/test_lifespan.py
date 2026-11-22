from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from api_view.app import create_app
from procurepilot.config import Settings


def test_lifespan_opens_and_closes_injected_container() -> None:
    events: list[str] = []
    marker = object()

    @asynccontextmanager
    async def factory(_settings):
        events.append("open")
        yield marker
        events.append("close")

    settings = Settings(
        app_env="test", mysql_dsn=None, agent_checkpoint_mysql_dsn=None
    )
    app = create_app(settings, container_factory=factory)
    assert events == []
    with TestClient(app) as client:
        assert client.app.state.container is marker
        assert events == ["open"]
    assert events == ["open", "close"]


def test_cors_allows_only_configured_frontend_origin() -> None:
    @asynccontextmanager
    async def factory(_settings):
        yield object()

    settings = Settings(
        app_env="test",
        mysql_dsn=None,
        agent_checkpoint_mysql_dsn=None,
        api_cors_origins=("http://127.0.0.1:3000",),
    )
    with TestClient(create_app(settings, container_factory=factory)) as client:
        allowed = client.options(
            "/api/history",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = client.options(
            "/api/history",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert "x-user-id" in allowed.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-origin" not in denied.headers
