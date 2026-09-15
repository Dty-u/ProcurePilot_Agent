import os
from typing import TypedDict
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agent.context import ProcurementContext
from agent.persistence import (
    ThreadNotFoundError,
    open_agent_persistence,
)
from procurepilot.config import Settings


class ResumeState(TypedDict, total=False):
    result: str


def context(user_id: str, thread_id: str) -> ProcurementContext:
    return ProcurementContext(
        user_id=user_id,
        roles=frozenset({"procurement_reader"}),
        thread_id=thread_id,
        trace_id=f"trace-{user_id}",
    )


def build_interrupt_graph(checkpointer):
    def ask_for_value(state: ResumeState) -> ResumeState:
        del state
        answer = interrupt({"kind": "supplement", "field": "supplier_id"})
        return {"result": str(answer)}

    builder = StateGraph(ResumeState)
    builder.add_node("ask", ask_for_value)
    builder.add_edge(START, "ask")
    builder.add_edge("ask", END)
    return builder.compile(checkpointer=checkpointer)


@pytest.mark.asyncio
async def test_mysql_checkpoint_resumes_after_persistence_is_reopened() -> None:
    checkpoint_dsn = os.getenv("AGENT_CHECKPOINT_MYSQL_DSN")
    if os.getenv("APP_ENV") != "test" or checkpoint_dsn is None:
        pytest.skip("需要 APP_ENV=test 和专用 AGENT_CHECKPOINT_MYSQL_DSN")
    database_name = urlsplit(checkpoint_dsn).path.strip("/").lower()
    if "test" not in database_name:
        pytest.skip("Checkpoint MySQL 数据库名必须包含 test")

    settings = Settings(
        _env_file=None,
        app_env="test",
        agent_checkpoint_mysql_dsn=checkpoint_dsn,
        agent_checkpoint_auto_setup=True,
    )
    owner = context("user-1", f"thread-{uuid4()}")
    config = {"configurable": {"thread_id": owner.thread_id}}

    async with open_agent_persistence(settings) as first:
        await first.threads.claim(owner)
        interrupted = await build_interrupt_graph(first.checkpointer).ainvoke({}, config)
        assert interrupted["__interrupt__"]

    async with open_agent_persistence(settings) as reopened:
        await reopened.threads.require_owner(owner)
        completed = await build_interrupt_graph(reopened.checkpointer).ainvoke(
            Command(resume="supplier-1"),
            config,
        )
        await reopened.checkpointer.adelete_thread(owner.thread_id)

    assert completed["result"] == "supplier-1"


@pytest.mark.asyncio
async def test_checkpoint_owner_rejects_other_and_unknown_users() -> None:
    settings = Settings(_env_file=None)
    async with open_agent_persistence(settings, in_memory=True) as persistence:
        await persistence.threads.claim(context("user-1", "thread-1"))

        with pytest.raises(PermissionError, match="owned by another user"):
            await persistence.threads.require_owner(context("user-2", "thread-1"))
        with pytest.raises(ThreadNotFoundError, match="thread was not registered"):
            await persistence.threads.require_owner(context("user-1", "missing-thread"))
