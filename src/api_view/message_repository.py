"""与 LangGraph Checkpoint 分离的脱敏展示消息仓储。"""

from __future__ import annotations

import asyncio
import builtins
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, Self

import aiomysql  # type: ignore[import-untyped]  # 第三方包未提供 py.typed
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from agent.context import ProcurementContext
from agent.persistence import mysql_connection_options
from mcp_server.context import SAFE_IDENTIFIER
from procurepilot.config import Settings

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*[^\s,;，；]+"
)
_CONNECTION_STRING = re.compile(
    r"(?i)\b(?:mysql(?:\+\w+)?|postgres(?:ql)?(?:\+\w+)?|redis)://[^\s,;，；]+"
)


class MessageConflictError(RuntimeError):
    """同一 thread_id 下的 message_id 已存在。"""


class DisplayMessage(BaseModel):
    """只包含前端回放所需的最小脱敏字段。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    thread_id: StrictStr = Field(pattern=SAFE_IDENTIFIER)
    message_id: StrictStr = Field(pattern=SAFE_IDENTIFIER)
    role: Literal["user", "assistant", "system", "tool"]
    content: StrictStr = Field(min_length=1, max_length=10000)
    occurred_at: datetime
    source: StrictStr = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_aware_timestamp(self) -> Self:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return self


@dataclass(frozen=True, slots=True)
class StoredDisplayMessage:
    user_id: str
    message: DisplayMessage


@dataclass(frozen=True, slots=True)
class DisplayThread:
    thread_id: str
    last_message_at: datetime
    message_count: int


class MessageStorage(Protocol):
    async def add(self, item: StoredDisplayMessage) -> None: ...

    async def list(self, user_id: str, thread_id: str) -> list[DisplayMessage]: ...

    async def delete(self, user_id: str, thread_id: str) -> int: ...

    async def list_threads(
        self, user_id: str, offset: int, limit: int
    ) -> builtins.list[DisplayThread]: ...


class InMemoryMessageStorage:
    """不执行外部 I/O 的展示消息测试替身。"""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], StoredDisplayMessage] = {}
        self._lock = asyncio.Lock()

    async def add(self, item: StoredDisplayMessage) -> None:
        key = (item.message.thread_id, item.message.message_id)
        async with self._lock:
            if key in self._items:
                raise MessageConflictError("message already exists in thread")
            self._items[key] = item

    async def list(self, user_id: str, thread_id: str) -> list[DisplayMessage]:
        messages = [
            item.message
            for item in self._items.values()
            if item.user_id == user_id and item.message.thread_id == thread_id
        ]
        return sorted(messages, key=lambda item: (item.occurred_at, item.message_id))

    async def delete(self, user_id: str, thread_id: str) -> int:
        async with self._lock:
            keys = [
                key
                for key, item in self._items.items()
                if item.user_id == user_id and item.message.thread_id == thread_id
            ]
            for key in keys:
                del self._items[key]
            return len(keys)

    async def list_threads(
        self, user_id: str, offset: int, limit: int
    ) -> builtins.list[DisplayThread]:
        grouped: dict[str, list[DisplayMessage]] = {}
        for item in self._items.values():
            if item.user_id == user_id:
                grouped.setdefault(item.message.thread_id, []).append(item.message)
        threads = [
            DisplayThread(thread_id, max(message.occurred_at for message in messages), len(messages))
            for thread_id, messages in grouped.items()
        ]
        return sorted(threads, key=lambda item: item.last_message_at, reverse=True)[
            offset : offset + limit
        ]


class MySQLMessageStorage:
    """使用 Agent MySQL 数据库持久化脱敏展示消息。"""

    def __init__(self, connection: aiomysql.Connection) -> None:
        self._connection = connection

    async def setup(self) -> None:
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS display_messages (
                    thread_id VARCHAR(128) NOT NULL,
                    message_id VARCHAR(128) NOT NULL,
                    user_id VARCHAR(128) NOT NULL,
                    role VARCHAR(32) NOT NULL,
                    content TEXT NOT NULL,
                    occurred_at VARCHAR(40) NOT NULL,
                    source VARCHAR(64) NOT NULL,
                    PRIMARY KEY (thread_id, message_id),
                    INDEX ix_display_messages_user_thread_time (
                        user_id, thread_id, occurred_at
                    )
                ) ENGINE=InnoDB
                """
            )

    async def add(self, item: StoredDisplayMessage) -> None:
        message = item.message
        try:
            async with self._connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO display_messages (
                        thread_id, message_id, user_id, role, content, occurred_at, source
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        message.thread_id,
                        message.message_id,
                        item.user_id,
                        message.role,
                        message.content,
                        message.occurred_at.astimezone(UTC).isoformat(),
                        message.source,
                    ),
                )
        except aiomysql.IntegrityError:
            raise MessageConflictError("message already exists in thread") from None

    async def list(self, user_id: str, thread_id: str) -> list[DisplayMessage]:
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT thread_id, message_id, role, content, occurred_at, source
                FROM display_messages
                WHERE user_id = %s AND thread_id = %s
                ORDER BY occurred_at, message_id
                """,
                (user_id, thread_id),
            )
            rows = await cursor.fetchall()
        return [
            DisplayMessage(
                thread_id=row[0],
                message_id=row[1],
                role=row[2],
                content=row[3],
                occurred_at=datetime.fromisoformat(row[4]),
                source=row[5],
            )
            for row in rows
        ]

    async def delete(self, user_id: str, thread_id: str) -> int:
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                "DELETE FROM display_messages WHERE user_id = %s AND thread_id = %s",
                (user_id, thread_id),
            )
            return int(cursor.rowcount)

    async def list_threads(
        self, user_id: str, offset: int, limit: int
    ) -> builtins.list[DisplayThread]:
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT thread_id, MAX(occurred_at), COUNT(*)
                FROM display_messages WHERE user_id = %s
                GROUP BY thread_id ORDER BY MAX(occurred_at) DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            rows = await cursor.fetchall()
        return [
            DisplayThread(row[0], datetime.fromisoformat(row[1]), int(row[2])) for row in rows
        ]


class MessageRepository:
    """通过可信用户和 thread_id 读取、写入、删除展示历史。"""

    def __init__(self, storage: MessageStorage) -> None:
        self._storage = storage

    async def add(
        self,
        context: ProcurementContext,
        message: DisplayMessage,
    ) -> DisplayMessage:
        self._require_current_thread(context, message.thread_id)
        sanitized = message.model_copy(update={"content": redact_message_content(message.content)})
        await self._storage.add(StoredDisplayMessage(context.user_id, sanitized))
        return sanitized

    async def list_messages(self, context: ProcurementContext) -> list[DisplayMessage]:
        return await self._storage.list(context.user_id, context.thread_id)

    async def delete_thread(self, context: ProcurementContext) -> int:
        return await self._storage.delete(context.user_id, context.thread_id)

    async def list_threads(
        self,
        context: ProcurementContext,
        *,
        offset: int,
        limit: int,
    ) -> list[DisplayThread]:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("invalid pagination")
        return await self._storage.list_threads(context.user_id, offset, limit)

    @staticmethod
    def _require_current_thread(context: ProcurementContext, thread_id: str) -> None:
        if thread_id != context.thread_id:
            raise PermissionError("message thread does not match trusted context")


def redact_message_content(content: str) -> str:
    """删除常见凭据赋值和数据库连接串，保留可展示文本。"""

    redacted = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", content)
    return _CONNECTION_STRING.sub("[REDACTED_DSN]", redacted)


@asynccontextmanager
async def open_message_repository(settings: Settings) -> AsyncIterator[MessageRepository]:
    """打开 Agent MySQL 展示历史连接，并按配置初始化表。"""

    connection_options = mysql_connection_options(settings)
    async with aiomysql.connect(**connection_options) as connection:
        storage = MySQLMessageStorage(connection)
        if settings.agent_checkpoint_auto_setup:
            await storage.setup()
        yield MessageRepository(storage)
