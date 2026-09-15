from datetime import UTC, datetime

import pytest

from agent.context import ProcurementContext
from api_view.message_repository import (
    DisplayMessage,
    InMemoryMessageStorage,
    MessageConflictError,
    MessageRepository,
)


def context(user_id: str, thread_id: str = "thread-1") -> ProcurementContext:
    return ProcurementContext(
        user_id=user_id,
        roles=frozenset({"procurement_reader"}),
        thread_id=thread_id,
        trace_id=f"trace-{user_id}",
    )


def message(message_id: str, content: str) -> DisplayMessage:
    return DisplayMessage(
        thread_id="thread-1",
        message_id=message_id,
        role="assistant",
        content=content,
        occurred_at=datetime(2026, 9, 13, 8, 0, tzinfo=UTC),
        source="procurepilot-main",
    )


@pytest.mark.asyncio
async def test_messages_round_trip_with_redaction_and_user_isolation() -> None:
    repository = MessageRepository(InMemoryMessageStorage())
    saved = await repository.add(
        context("user-1"),
        message("message-1", "结果完成，API_KEY=top-secret，DSN=mysql://u:p@db/dev"),
    )
    first_user = await repository.list_messages(context("user-1"))
    other_user = await repository.list_messages(context("user-2"))

    assert "top-secret" not in saved.content
    assert "mysql://" not in saved.content
    assert first_user == [saved]
    assert other_user == []


@pytest.mark.asyncio
async def test_duplicate_message_id_in_thread_is_rejected() -> None:
    repository = MessageRepository(InMemoryMessageStorage())
    await repository.add(context("user-1"), message("message-1", "first"))

    with pytest.raises(MessageConflictError, match="message already exists"):
        await repository.add(context("user-1"), message("message-1", "second"))


@pytest.mark.asyncio
async def test_deleting_display_history_does_not_delete_another_user() -> None:
    repository = MessageRepository(InMemoryMessageStorage())
    await repository.add(context("user-1"), message("message-1", "first"))
    await repository.add(context("user-2"), message("message-2", "second"))

    deleted = await repository.delete_thread(context("user-1"))
    first_user = await repository.list_messages(context("user-1"))
    other_user = await repository.list_messages(context("user-2"))

    assert deleted == 1
    assert first_user == []
    assert [item.message_id for item in other_user] == ["message-2"]
