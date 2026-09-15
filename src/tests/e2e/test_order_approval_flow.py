from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.context import ProcurementContext
from agent.persistence import AgentPersistence, ThreadOwnershipRepository
from agent.resume_service import (
    InMemoryResumeStorage,
    PendingInterrupt,
    ResumeService,
    hash_parameter_summary,
)
from api_view.app import create_app
from api_view.message_repository import InMemoryMessageStorage, MessageRepository
from procurepilot.business.enums import OrderAction
from procurepilot.config import Settings


def test_reject_is_zero_write_approve_is_once_and_resume_is_one_shot() -> None:
    writes: list[str] = []

    class Graph:
        async def astream(self, command, **_kwargs):
            decision = command.resume["decisions"][0]["type"]
            if decision == "approve":
                writes.append("created")
            yield "messages", {"type": "token", "text": decision}

    store = InMemoryStore()
    resumes = ResumeService(InMemoryResumeStorage())
    container = SimpleNamespace(
        persistence=AgentPersistence(
            InMemorySaver(), store, ThreadOwnershipRepository(store)
        ),
        resumes=resumes,
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
    headers = {"x-user-id": "u-1", "x-roles": "order_executor"}
    now = datetime.now(UTC)
    context = ProcurementContext(
        user_id="u-1",
        roles=frozenset({"order_executor"}),
        thread_id="order-1",
        trace_id="setup-1",
    )

    async def prepare() -> None:
        await container.persistence.threads.claim(context)
        for interrupt_id in ("reject-1", "approve-1"):
            await resumes.register(
                context,
                PendingInterrupt(
                    interrupt_id=interrupt_id,
                    thread_id="order-1",
                    order_action=OrderAction.CREATE,
                    resume_kind="decision",
                    parameter_summary_hash=hash_parameter_summary({"part": "P-1"}),
                    created_at=now,
                    expires_at=now + timedelta(minutes=10),
                ),
            )

    import asyncio

    asyncio.run(prepare())
    with TestClient(create_app(settings, container_factory=factory)) as client:
        rejected = client.post(
            "/api/chat/order-1/resume",
            headers=headers,
            json={"interrupt_id": "reject-1", "resume": {"kind": "decision", "decision": "reject"}},
        )
        approved = client.post(
            "/api/chat/order-1/resume",
            headers=headers,
            json={"interrupt_id": "approve-1", "resume": {"kind": "decision", "decision": "approve"}},
        )
        repeated = client.post(
            "/api/chat/order-1/resume",
            headers=headers,
            json={"interrupt_id": "approve-1", "resume": {"kind": "decision", "decision": "approve"}},
        )

    assert rejected.status_code == approved.status_code == 200
    assert writes == ["created"]
    assert repeated.status_code == 409
