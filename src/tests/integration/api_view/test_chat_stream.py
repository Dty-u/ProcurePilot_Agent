from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, Interrupt

from agent.persistence import AgentPersistence, ThreadOwnershipRepository
from agent.resume_service import InMemoryResumeStorage, ResumeService
from api_view.app import create_app
from api_view.message_repository import InMemoryMessageStorage, MessageRepository
from procurepilot.config import Settings


class Graph:
    async def astream(self, *_args, **_kwargs):
        yield "messages", {"type": "token", "text": "报价 Q-1"}


class Container:
    def __init__(self) -> None:
        store = InMemoryStore()
        self.persistence = AgentPersistence(
            InMemorySaver(), store, ThreadOwnershipRepository(store)
        )
        self.resumes = ResumeService(InMemoryResumeStorage())
        self.messages = MessageRepository(InMemoryMessageStorage())

    @asynccontextmanager
    async def open_agent(self, _context):
        yield SimpleNamespace(graph=Graph())


def test_chat_stream_uses_trusted_headers_and_persists_display_history() -> None:
    container = Container()

    @asynccontextmanager
    async def factory(_settings):
        yield container

    settings = Settings(
        app_env="test", mysql_dsn=None, agent_checkpoint_mysql_dsn=None
    )
    headers = {"x-user-id": "u-1", "x-roles": "procurement_reader"}
    with TestClient(create_app(settings, container_factory=factory)) as client:
        response = client.post(
            "/api/chat/stream",
            headers=headers,
            json={"message": "比价", "thread_id": "t-1"},
        )
        history = client.get("/api/history/t-1", headers=headers)

    assert response.status_code == 200
    assert "event: token" in response.text
    assert "event: done" in response.text
    assert "报价 Q-1" in response.text
    assert history.status_code == 200
    assert [item["role"] for item in history.json()["items"]] == ["user", "assistant"]


def test_chat_rejects_model_supplied_identity_and_missing_auth() -> None:
    container = Container()

    @asynccontextmanager
    async def factory(_settings):
        yield container

    settings = Settings(
        app_env="test", mysql_dsn=None, agent_checkpoint_mysql_dsn=None
    )
    with TestClient(create_app(settings, container_factory=factory)) as client:
        forged = client.post(
            "/api/chat/stream",
            json={"message": "api_key=must-not-echo", "user_id": "admin"},
        )
        missing = client.post("/api/chat/stream", json={"message": "hi"})

    assert forged.status_code == 422
    assert "must-not-echo" not in forged.text
    assert missing.status_code == 401


def test_order_interrupt_is_registered_before_it_is_streamed() -> None:
    class InterruptGraph:
        async def astream(self, graph_input, **_kwargs):
            if isinstance(graph_input, Command):
                yield "messages", {"type": "token", "text": "supplemented"}
                return
            yield "values", {
                "__interrupt__": [
                    Interrupt(
                        id="interrupt-1",
                        value={
                            "kind": "order_info_request",
                            "missing_fields": ["supplier_id"],
                            "confirmed_summary": {"action": "create"},
                        },
                    )
                ]
            }

    container = Container()

    @asynccontextmanager
    async def open_agent(_context):
        yield SimpleNamespace(graph=InterruptGraph())

    container.open_agent = open_agent  # type: ignore[method-assign]

    @asynccontextmanager
    async def factory(_settings):
        yield container

    settings = Settings(app_env="test", mysql_dsn=None, agent_checkpoint_mysql_dsn=None)
    headers = {"x-user-id": "u-1", "x-roles": "order_executor"}
    with TestClient(create_app(settings, container_factory=factory)) as client:
        interrupted = client.post(
            "/api/chat/stream",
            headers=headers,
            json={"message": "创建订单", "thread_id": "t-2"},
        )
        resumed = client.post(
            "/api/chat/t-2/resume",
            headers=headers,
            json={
                "interrupt_id": "interrupt-1",
                "resume": {"kind": "supplement", "supplement": '{"supplier_id":"S-1"}'},
            },
        )

    assert "event: interrupt" in interrupted.text
    assert resumed.status_code == 200
    assert "supplemented" in resumed.text
