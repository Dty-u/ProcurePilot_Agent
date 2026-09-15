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
