"""Agent Checkpoint 与用户 Store 的 MySQL 生命周期。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import aiomysql  # type: ignore[import-untyped]  # 第三方包未提供 py.typed
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.mysql.aio import AIOMySQLStore

from agent.context import ProcurementContext
from procurepilot.config import Settings

_THREAD_OWNER_NAMESPACE = ("procurepilot", "thread_owners")


class ThreadNotFoundError(LookupError):
    """请求的 thread_id 尚未登记。"""


class ThreadOwnershipRepository:
    """在读取 Checkpoint 前强制验证 thread_id 对应的可信用户。"""

    def __init__(self, store: BaseStore) -> None:
        self._store = store
        self._lock = asyncio.Lock()

    async def claim(self, context: ProcurementContext) -> None:
        async with self._lock:
            item = await self._store.aget(_THREAD_OWNER_NAMESPACE, context.thread_id)
            if item is None:
                await self._store.aput(
                    _THREAD_OWNER_NAMESPACE,
                    context.thread_id,
                    {"user_id": context.user_id},
                )
                return
            self._assert_owner(item.value.get("user_id"), context.user_id)

    async def require_owner(self, context: ProcurementContext) -> None:
        item = await self._store.aget(_THREAD_OWNER_NAMESPACE, context.thread_id)
        if item is None:
            raise ThreadNotFoundError("thread was not registered")
        self._assert_owner(item.value.get("user_id"), context.user_id)

    @staticmethod
    def _assert_owner(stored_user_id: object, current_user_id: str) -> None:
        if stored_user_id != current_user_id:
            raise PermissionError("thread is owned by another user")


@dataclass(slots=True)
class AgentPersistence:
    """一个应用生命周期内已打开的 Checkpoint 与 Store 资源。"""

    checkpointer: BaseCheckpointSaver[Any]
    store: BaseStore
    threads: ThreadOwnershipRepository


def mysql_connection_options(settings: Settings) -> dict[str, Any]:
    """返回不写入日志的 Agent MySQL 连接参数。"""

    dsn = settings.require_checkpoint_mysql_dsn().get_secret_value()
    return {
        **AIOMySQLSaver.parse_conn_string(dsn),
        "autocommit": True,
        "connect_timeout": settings.mysql_connect_timeout_seconds,
    }


@asynccontextmanager
async def open_agent_persistence(
    settings: Settings,
    *,
    in_memory: bool = False,
) -> AsyncIterator[AgentPersistence]:
    """显式打开并可靠关闭 MySQL Checkpointer 与 MySQL Store。"""

    if in_memory:
        memory_store = InMemoryStore()
        yield AgentPersistence(
            checkpointer=InMemorySaver(),
            store=memory_store,
            threads=ThreadOwnershipRepository(memory_store),
        )
        return

    connection_options = mysql_connection_options(settings)

    async with AsyncExitStack() as stack:
        checkpoint_connection = await stack.enter_async_context(
            aiomysql.connect(**connection_options)
        )
        store_connection = await stack.enter_async_context(
            aiomysql.connect(**connection_options)
        )
        checkpointer = AIOMySQLSaver(checkpoint_connection)
        store = AIOMySQLStore(store_connection)
        if settings.agent_checkpoint_auto_setup:
            await checkpointer.setup()
            await store.setup()
        yield AgentPersistence(
            checkpointer=checkpointer,
            store=store,
            threads=ThreadOwnershipRepository(store),
        )
