from contextlib import asynccontextmanager

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.persistence import open_agent_persistence
from procurepilot.config import Settings


def settings_for() -> Settings:
    return Settings(
        _env_file=None,
        agent_checkpoint_mysql_dsn=(
            "mysql+aiomysql://checkpoint:secret@localhost/procurepilot_checkpoint_dev"
        ),
    )


@pytest.mark.asyncio
async def test_missing_agent_mysql_dsn_fails_before_connecting() -> None:
    settings = Settings(_env_file=None)

    with pytest.raises(ValueError, match="AGENT_CHECKPOINT_MYSQL_DSN is required"):
        async with open_agent_persistence(settings):
            raise AssertionError("缺少 Agent MySQL DSN 时不能进入持久化生命周期")


@pytest.mark.asyncio
async def test_persistence_uses_mysql_checkpoint_and_store_and_closes_resources(
    monkeypatch,
) -> None:
    import agent.persistence as persistence_module

    lifecycle: dict[str, object] = {
        "connects": [],
        "checkpoint_setup": False,
        "store_setup": False,
        "closed": [],
    }
    connections = [object(), object()]

    class Checkpointer:
        def __init__(self, conn) -> None:
            assert conn is connections[0]

        @staticmethod
        def parse_conn_string(_dsn: str) -> dict[str, object]:
            return {
                "host": "localhost",
                "user": "checkpoint",
                "password": "secret",
                "db": "procurepilot_checkpoint_dev",
                "port": 3306,
                "unix_socket": None,
            }

        async def setup(self) -> None:
            lifecycle["checkpoint_setup"] = True

    class Store:
        def __init__(self, conn) -> None:
            assert conn is connections[1]

        async def setup(self) -> None:
            lifecycle["store_setup"] = True

    @asynccontextmanager
    async def connection_context(index: int, **kwargs):
        connects = lifecycle["connects"]
        assert isinstance(connects, list)
        connects.append(kwargs)
        try:
            yield connections[index]
        finally:
            closed = lifecycle["closed"]
            assert isinstance(closed, list)
            closed.append(index)

    connect_index = 0

    def connect(**kwargs):
        nonlocal connect_index
        index = connect_index
        connect_index += 1
        return connection_context(index, **kwargs)

    monkeypatch.setattr(persistence_module.aiomysql, "connect", connect)
    monkeypatch.setattr(persistence_module, "AIOMySQLSaver", Checkpointer)
    monkeypatch.setattr(persistence_module, "AIOMySQLStore", Store)
    settings = settings_for().model_copy(update={"agent_checkpoint_auto_setup": True})

    async with open_agent_persistence(settings) as persistence:
        assert isinstance(persistence.store, Store)

    expected_connect = {
        "host": "localhost",
        "user": "checkpoint",
        "password": "secret",
        "db": "procurepilot_checkpoint_dev",
        "port": 3306,
        "unix_socket": None,
        "autocommit": True,
        "connect_timeout": 10,
    }
    assert lifecycle == {
        "connects": [expected_connect, expected_connect],
        "checkpoint_setup": True,
        "store_setup": True,
        "closed": [1, 0],
    }


@pytest.mark.asyncio
async def test_in_memory_mode_uses_no_external_database() -> None:
    async with open_agent_persistence(settings_for(), in_memory=True) as persistence:
        assert isinstance(persistence.checkpointer, InMemorySaver)
        assert isinstance(persistence.store, InMemoryStore)
        await persistence.store.aput(("probe",), "key", {"ready": True})
        item = await persistence.store.aget(("probe",), "key")
        assert item is not None and item.value == {"ready": True}


@pytest.mark.asyncio
async def test_store_setup_failure_closes_both_mysql_connections(monkeypatch) -> None:
    import agent.persistence as persistence_module

    closed: list[int] = []
    connections = [object(), object()]

    class Checkpointer:
        def __init__(self, _connection) -> None:
            pass

        @staticmethod
        def parse_conn_string(_dsn: str) -> dict[str, object]:
            return {}

        async def setup(self) -> None:
            return None

    class Store:
        def __init__(self, _connection) -> None:
            pass

        async def setup(self) -> None:
            raise RuntimeError("setup failed")

    @asynccontextmanager
    async def connection_context(index: int, **_kwargs):
        try:
            yield connections[index]
        finally:
            closed.append(index)

    connect_index = 0

    def connect(**kwargs):
        nonlocal connect_index
        index = connect_index
        connect_index += 1
        return connection_context(index, **kwargs)

    monkeypatch.setattr(persistence_module.aiomysql, "connect", connect)
    monkeypatch.setattr(persistence_module, "AIOMySQLSaver", Checkpointer)
    monkeypatch.setattr(persistence_module, "AIOMySQLStore", Store)

    with pytest.raises(RuntimeError, match="setup failed"):
        async with open_agent_persistence(
            settings_for().model_copy(update={"agent_checkpoint_auto_setup": True})
        ):
            raise AssertionError("setup failure must prevent entering the context")

    assert closed == [1, 0]
