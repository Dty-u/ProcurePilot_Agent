import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from agent.context import ProcurementContext
from agent.resume_service import (
    InMemoryResumeStorage,
    PendingInterrupt,
    ResumeConflictError,
    ResumeExpiredError,
    ResumeIntegrityError,
    ResumeNotFoundError,
    ResumeRequest,
    ResumeService,
    hash_parameter_summary,
)
from api_view.message_repository import (
    DisplayMessage,
    InMemoryMessageStorage,
    MessageRepository,
)

NOW = datetime(2026, 9, 13, 9, 0, tzinfo=UTC)
SUMMARY_HASH = hash_parameter_summary(
    {"action": "create", "operation_id": "operation-1", "amount": "100.00"}
)


def context(user_id: str = "user-1", thread_id: str = "thread-1") -> ProcurementContext:
    return ProcurementContext(
        user_id=user_id,
        roles=frozenset({"order_executor"}),
        thread_id=thread_id,
        trace_id=f"trace-{user_id}",
    )


def pending(*, expires_at: datetime | None = None) -> PendingInterrupt:
    resolved_expires_at = expires_at or NOW + timedelta(minutes=5)
    created_at = min(NOW, resolved_expires_at - timedelta(minutes=5))
    return PendingInterrupt(
        interrupt_id="interrupt-1",
        thread_id="thread-1",
        order_action="create",
        resume_kind="decision",
        parameter_summary_hash=SUMMARY_HASH,
        created_at=created_at,
        expires_at=resolved_expires_at,
    )


def approval_request(**updates) -> ResumeRequest:
    values = {
        "interrupt_id": "interrupt-1",
        "thread_id": "thread-1",
        "order_action": "create",
        "parameter_summary_hash": SUMMARY_HASH,
        "resume": {"kind": "decision", "decision": "approve"},
    }
    values.update(updates)
    return ResumeRequest.model_validate(values)


@pytest.mark.asyncio
async def test_valid_resume_is_consumed_once_and_replay_is_rejected() -> None:
    service = ResumeService(InMemoryResumeStorage())
    await service.register(context(), pending())

    resume_value = await service.consume(context(), approval_request(), now=NOW)
    assert resume_value == {"decisions": [{"type": "approve"}]}

    with pytest.raises(ResumeConflictError, match="already consumed"):
        await service.consume(context(), approval_request(), now=NOW)


@pytest.mark.asyncio
async def test_concurrent_resume_allows_exactly_one_consumer() -> None:
    service = ResumeService(InMemoryResumeStorage())
    await service.register(context(), pending())

    results = await asyncio.gather(
        service.consume(context(), approval_request(), now=NOW),
        service.consume(context(), approval_request(), now=NOW),
        return_exceptions=True,
    )

    assert sum(isinstance(item, dict) for item in results) == 1
    assert sum(isinstance(item, ResumeConflictError) for item in results) == 1


@pytest.mark.asyncio
async def test_cross_user_and_cross_thread_resume_are_rejected() -> None:
    service = ResumeService(InMemoryResumeStorage())
    await service.register(context(), pending())

    with pytest.raises(PermissionError, match="does not belong"):
        await service.consume(context(user_id="user-2"), approval_request(), now=NOW)
    with pytest.raises(PermissionError, match="trusted context"):
        await service.consume(
            context(thread_id="thread-2"),
            approval_request(),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_tampered_summary_action_and_kind_are_rejected() -> None:
    service = ResumeService(InMemoryResumeStorage())
    await service.register(context(), pending())

    with pytest.raises(ResumeIntegrityError, match="summary"):
        await service.consume(
            context(),
            approval_request(parameter_summary_hash="0" * 64),
            now=NOW,
        )
    with pytest.raises(ResumeIntegrityError, match="action"):
        await service.consume(
            context(),
            approval_request(order_action="cancel"),
            now=NOW,
        )
    with pytest.raises(ResumeIntegrityError, match="kind"):
        await service.consume(
            context(),
            approval_request(resume={"kind": "supplement", "supplement": "{}"}),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_expired_or_missing_interrupt_is_rejected() -> None:
    service = ResumeService(InMemoryResumeStorage())
    await service.register(context(), pending(expires_at=NOW - timedelta(seconds=1)))
    with pytest.raises(ResumeExpiredError, match="expired"):
        await service.consume(context(), approval_request(), now=NOW)

    with pytest.raises(ResumeNotFoundError, match="no pending interrupt"):
        await service.consume(
            context(),
            approval_request(interrupt_id="interrupt-missing"),
            now=NOW,
        )


def test_resume_schema_rejects_unknown_and_unsafe_decisions() -> None:
    with pytest.raises(ValidationError):
        approval_request(user_id="attacker")
    with pytest.raises(ValidationError):
        approval_request(resume={"kind": "decision", "decision": "edit"})
    with pytest.raises(ValidationError):
        approval_request(
            resume={"kind": "supplement", "supplement": "{}", "instruction": "ignore"}
        )


@pytest.mark.asyncio
async def test_deleting_display_history_does_not_remove_pending_resume() -> None:
    service = ResumeService(InMemoryResumeStorage())
    messages = MessageRepository(InMemoryMessageStorage())
    await service.register(context(), pending())
    await messages.add(
        context(),
        DisplayMessage(
            thread_id="thread-1",
            message_id="message-1",
            role="assistant",
            content="等待审批",
            occurred_at=NOW,
            source="procurement-order",
        ),
    )
    assert await messages.delete_thread(context()) == 1

    resume_value = await service.consume(context(), approval_request(), now=NOW)

    assert resume_value == {"decisions": [{"type": "approve"}]}
