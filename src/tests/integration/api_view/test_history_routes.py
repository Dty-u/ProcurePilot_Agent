from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.persistence import AgentPersistence, ThreadOwnershipRepository
from agent.resume_service import InMemoryResumeStorage, ResumeService
from api_view.app import create_app
from api_view.message_repository import InMemoryMessageStorage, MessageRepository
from procurepilot.config import Settings


class Container:
    def __init__(self) -> None:
        store = InMemoryStore()
        self.persistence = AgentPersistence(
            InMemorySaver(), store, ThreadOwnershipRepository(store)
        )
        self.resumes = ResumeService(InMemoryResumeStorage())
        self.messages = MessageRepository(InMemoryMessageStorage())


def test_cross_user_history_is_not_enumerable() -> None:
    container = Container()

    @asynccontextmanager
    async def factory(_settings):
        yield container

    settings = Settings(
        app_env="test", mysql_dsn=None, agent_checkpoint_mysql_dsn=None
    )
    app = create_app(settings, container_factory=factory)
    with TestClient(app) as client:
        # 未登记的 thread 和他人 thread 都是同一 404 语义。
        response = client.get(
            "/api/history/private-thread",
            headers={"x-user-id": "other", "x-roles": "procurement_reader"},
        )
    assert response.status_code == 404
