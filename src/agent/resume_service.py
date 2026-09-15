"""一次性、安全且与展示历史分离的 Agent 中断恢复网关。"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol, Self

import aiomysql  # type: ignore[import-untyped]  # 第三方包未提供 py.typed
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from agent.context import ProcurementContext
from agent.persistence import mysql_connection_options
from mcp_server.context import SAFE_IDENTIFIER
from procurepilot.business.enums import OrderAction
from procurepilot.config import Settings

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ResumeNotFoundError(LookupError):
    """当前线程没有对应的待恢复中断。"""


class ResumeConflictError(RuntimeError):
    """中断已经消费或 interrupt_id 重复。"""


class ResumeExpiredError(RuntimeError):
    """中断已过期。"""


class ResumeIntegrityError(RuntimeError):
    """恢复动作与登记时的操作摘要不一致。"""


class ResumeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SupplementResume(ResumeModel):
    kind: Literal["supplement"]
    supplement: StrictStr = Field(min_length=2, max_length=10000)


class DecisionResume(ResumeModel):
    kind: Literal["decision"]
    decision: Literal["approve", "reject"]
    message: StrictStr | None = Field(default=None, min_length=1, max_length=500)


class ResumeRequest(ResumeModel):
    interrupt_id: StrictStr = Field(pattern=SAFE_IDENTIFIER)
    thread_id: StrictStr = Field(pattern=SAFE_IDENTIFIER)
    order_action: OrderAction
    parameter_summary_hash: StrictStr = Field(pattern=_SHA256_PATTERN)
    resume: Annotated[SupplementResume | DecisionResume, Field(discriminator="kind")]


class PendingInterrupt(ResumeModel):
    interrupt_id: StrictStr = Field(pattern=SAFE_IDENTIFIER)
    thread_id: StrictStr = Field(pattern=SAFE_IDENTIFIER)
    order_action: OrderAction
    resume_kind: Literal["supplement", "decision"]
    parameter_summary_hash: StrictStr = Field(pattern=_SHA256_PATTERN)
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_times(self) -> Self:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        return self


@dataclass(frozen=True, slots=True)
class StoredInterrupt:
    interrupt_id: str
    user_id: str
    thread_id: str
    order_action: str
    resume_kind: str
    parameter_summary_hash: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None


class ResumeStorage(Protocol):
    async def add(self, interrupt: StoredInterrupt) -> None: ...

    async def get(self, interrupt_id: str) -> StoredInterrupt | None: ...

    async def mark_consumed(self, interrupt_id: str, consumed_at: datetime) -> bool: ...


class InMemoryResumeStorage:
    """不执行外部 I/O 的测试替身，保持与 MySQL 相同的一次性语义。"""

    def __init__(self) -> None:
        self._items: dict[str, StoredInterrupt] = {}
        self._lock = asyncio.Lock()

    async def add(self, interrupt: StoredInterrupt) -> None:
        async with self._lock:
            if interrupt.interrupt_id in self._items:
                raise ResumeConflictError("interrupt_id already exists")
            self._items[interrupt.interrupt_id] = interrupt

    async def get(self, interrupt_id: str) -> StoredInterrupt | None:
        return self._items.get(interrupt_id)

    async def mark_consumed(self, interrupt_id: str, consumed_at: datetime) -> bool:
        async with self._lock:
            current = self._items.get(interrupt_id)
            if current is None or current.consumed_at is not None:
                return False
            self._items[interrupt_id] = replace(current, consumed_at=consumed_at)
            return True


class MySQLResumeStorage:
    """在 Agent MySQL 数据库中保存并原子消费恢复元数据。"""

    def __init__(self, connection: aiomysql.Connection) -> None:
        self._connection = connection

    async def setup(self) -> None:
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_interrupts (
                    interrupt_id VARCHAR(128) PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    thread_id VARCHAR(128) NOT NULL,
                    order_action VARCHAR(32) NOT NULL,
                    resume_kind VARCHAR(32) NOT NULL,
                    parameter_summary_hash CHAR(64) NOT NULL,
                    created_at VARCHAR(40) NOT NULL,
                    expires_at VARCHAR(40) NOT NULL,
                    consumed_at VARCHAR(40) NULL,
                    INDEX ix_pending_interrupts_user_thread (
                        user_id, thread_id, consumed_at
                    )
                ) ENGINE=InnoDB
                """
            )

    async def add(self, interrupt: StoredInterrupt) -> None:
        try:
            async with self._connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO pending_interrupts (
                        interrupt_id, user_id, thread_id, order_action, resume_kind,
                        parameter_summary_hash, created_at, expires_at, consumed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL)
                    """,
                    (
                        interrupt.interrupt_id,
                        interrupt.user_id,
                        interrupt.thread_id,
                        interrupt.order_action,
                        interrupt.resume_kind,
                        interrupt.parameter_summary_hash,
                        interrupt.created_at.astimezone(UTC).isoformat(),
                        interrupt.expires_at.astimezone(UTC).isoformat(),
                    ),
                )
        except aiomysql.IntegrityError:
            raise ResumeConflictError("interrupt_id already exists") from None

    async def get(self, interrupt_id: str) -> StoredInterrupt | None:
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT interrupt_id, user_id, thread_id, order_action, resume_kind,
                       parameter_summary_hash, created_at, expires_at, consumed_at
                FROM pending_interrupts WHERE interrupt_id = %s
                """,
                (interrupt_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return StoredInterrupt(
            interrupt_id=row[0],
            user_id=row[1],
            thread_id=row[2],
            order_action=row[3],
            resume_kind=row[4],
            parameter_summary_hash=row[5],
            created_at=datetime.fromisoformat(row[6]),
            expires_at=datetime.fromisoformat(row[7]),
            consumed_at=datetime.fromisoformat(row[8]) if row[8] is not None else None,
        )

    async def mark_consumed(self, interrupt_id: str, consumed_at: datetime) -> bool:
        async with self._connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE pending_interrupts SET consumed_at = %s
                WHERE interrupt_id = %s AND consumed_at IS NULL
                """,
                (consumed_at.astimezone(UTC).isoformat(), interrupt_id),
            )
            return int(cursor.rowcount) == 1


def hash_parameter_summary(summary: dict[str, Any]) -> str:
    """对已展示给用户的规范化参数摘要生成稳定 SHA-256。"""

    canonical = json.dumps(
        summary,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ResumeService:
    """验证可信上下文，并通过存储适配器原子消费 interrupt_id。"""

    def __init__(self, storage: ResumeStorage) -> None:
        self._storage = storage

    async def register(
        self,
        context: ProcurementContext,
        pending: PendingInterrupt,
    ) -> None:
        self._require_context_thread(context, pending.thread_id)
        await self._storage.add(
            StoredInterrupt(
                interrupt_id=pending.interrupt_id,
                user_id=context.user_id,
                thread_id=pending.thread_id,
                order_action=pending.order_action.value,
                resume_kind=pending.resume_kind,
                parameter_summary_hash=pending.parameter_summary_hash,
                created_at=pending.created_at.astimezone(UTC),
                expires_at=pending.expires_at.astimezone(UTC),
            )
        )

    async def consume(
        self,
        context: ProcurementContext,
        request: ResumeRequest,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        self._require_context_thread(context, request.thread_id)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")

        stored = await self._storage.get(request.interrupt_id)
        if stored is None:
            raise ResumeNotFoundError("no pending interrupt for interrupt_id")
        self._validate_stored(context, request, stored, now)
        consumed_at = now.astimezone(UTC)
        if not await self._storage.mark_consumed(request.interrupt_id, consumed_at):
            raise ResumeConflictError("interrupt was already consumed")
        return self._to_langgraph_resume(request.resume)

    async def consume_public(
        self,
        context: ProcurementContext,
        interrupt_id: str,
        resume: SupplementResume | DecisionResume,
        *,
        now: datetime,
    ) -> dict[str, Any]:
        """HTTP 边界只接收决定，操作类型和摘要从服务端记录读取。"""

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        stored = await self._storage.get(interrupt_id)
        if stored is None:
            raise ResumeNotFoundError("no pending interrupt for interrupt_id")
        if stored.user_id != context.user_id or stored.thread_id != context.thread_id:
            raise PermissionError("interrupt does not belong to current user and thread")
        if stored.consumed_at is not None:
            raise ResumeConflictError("interrupt was already consumed")
        if stored.expires_at <= now.astimezone(UTC):
            raise ResumeExpiredError("interrupt has expired")
        if stored.resume_kind != resume.kind:
            raise ResumeIntegrityError("resume kind does not match pending interrupt")
        if not await self._storage.mark_consumed(interrupt_id, now.astimezone(UTC)):
            raise ResumeConflictError("interrupt was already consumed")
        return self._to_langgraph_resume(resume)

    @staticmethod
    def _validate_stored(
        context: ProcurementContext,
        request: ResumeRequest,
        stored: StoredInterrupt,
        now: datetime,
    ) -> None:
        if stored.user_id != context.user_id:
            raise PermissionError("interrupt does not belong to current user")
        if stored.thread_id != context.thread_id:
            raise PermissionError("interrupt does not belong to trusted context thread")
        if stored.consumed_at is not None:
            raise ResumeConflictError("interrupt was already consumed")
        if stored.expires_at <= now.astimezone(UTC):
            raise ResumeExpiredError("interrupt has expired")
        if stored.order_action != request.order_action.value:
            raise ResumeIntegrityError("resume action does not match pending interrupt")
        if stored.resume_kind != request.resume.kind:
            raise ResumeIntegrityError("resume kind does not match pending interrupt")
        if not hmac.compare_digest(
            stored.parameter_summary_hash,
            request.parameter_summary_hash,
        ):
            raise ResumeIntegrityError("parameter summary does not match pending interrupt")

    @staticmethod
    def _to_langgraph_resume(resume: SupplementResume | DecisionResume) -> dict[str, Any]:
        if isinstance(resume, SupplementResume):
            return {"supplement": resume.supplement}
        decision: dict[str, str] = {"type": resume.decision}
        if resume.message is not None:
            decision["message"] = resume.message
        return {"decisions": [decision]}

    @staticmethod
    def _require_context_thread(context: ProcurementContext, thread_id: str) -> None:
        if thread_id != context.thread_id:
            raise PermissionError("thread_id does not match trusted context")


@asynccontextmanager
async def open_resume_service(settings: Settings) -> AsyncIterator[ResumeService]:
    """打开 Agent MySQL 恢复元数据连接，并按配置初始化表。"""

    connection_options = mysql_connection_options(settings)
    async with aiomysql.connect(**connection_options) as connection:
        storage = MySQLResumeStorage(connection)
        if settings.agent_checkpoint_auto_setup:
            await storage.setup()
        yield ResumeService(storage)
