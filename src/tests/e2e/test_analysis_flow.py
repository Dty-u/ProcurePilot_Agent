from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.persistence import AgentPersistence, ThreadOwnershipRepository
from agent.resume_service import InMemoryResumeStorage, ResumeService
from api_view.app import create_app
from api_view.message_repository import InMemoryMessageStorage, MessageRepository
from procurepilot.config import Settings


def test_analysis_flow_preserves_evidence_in_stream() -> None:
    class Graph:
        async def astream(self, *_args, **_kwargs):
            yield "messages", {"type": "tool_start", "tool_name": "quotation_query"}
            yield "messages", {
                "type": "tool_result",
                "tool_name": "quotation_query",
                "content": "Q-100 | ERP | 2026-09-15T08:00:00Z",
            }
            yield "messages", {"type": "token", "text": "建议选择 Q-100"}

    store = InMemoryStore()
    container = SimpleNamespace(
        persistence=AgentPersistence(
            InMemorySaver(), store, ThreadOwnershipRepository(store)
        ),
        resumes=ResumeService(InMemoryResumeStorage()),
        messages=MessageRepository(InMemoryMessageStorage()),
    )

    @asynccontextmanager
    async def open_agent(_context):
        yield SimpleNamespace(graph=Graph())

    container.open_agent = open_agent

    @asynccontextmanager
    async def factory(_settings):
        yield container

    settings = Settings(app_env="test", mysql_dsn=None, agent_checkpoint_mysql_dsn=None)
    with TestClient(create_app(settings, container_factory=factory)) as client:
        response = client.post(
            "/api/chat/stream",
            headers={"x-user-id": "u-1", "x-roles": "procurement_reader"},
            json={"message": "比较报价", "thread_id": "analysis-1"},
        )

    assert response.status_code == 200
    assert all(value in response.text for value in ("Q-100", "ERP", "2026-09-15"))
    assert response.text.index("tool_start") < response.text.index("tool_result")
