from datetime import UTC, datetime, timedelta

import pytest

from procurepilot.business.approval import ApprovalGrant
from procurepilot.business.enums import OrderAction
from procurepilot.business.errors import ApprovalRequiredError, ConflictError, PermissionDeniedError

NOW = datetime(2026, 9, 9, tzinfo=UTC)


def grant(**overrides) -> ApprovalGrant:
    values = {
        "approval_id": "approval-1",
        "operation_id": "operation-1",
        "approver_user_id": "user-1",
        "thread_id": "thread-1",
        "action": OrderAction.CREATE,
        "payload_hash": "a" * 64,
        "decision": "approve",
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
        "consumed_at": None,
    }
    values.update(overrides)
    return ApprovalGrant(**values)


def test_valid_grant_is_consumed_once() -> None:
    consumed = grant().authorize_and_consume(
        operation_id="operation-1",
        user_id="user-1",
        thread_id="thread-1",
        action=OrderAction.CREATE,
        payload_hash="a" * 64,
        at=NOW + timedelta(seconds=1),
    )

    assert consumed.consumed_at == NOW + timedelta(seconds=1)
    with pytest.raises(ConflictError):
        consumed.authorize_and_consume(
            operation_id="operation-1",
            user_id="user-1",
            thread_id="thread-1",
            action=OrderAction.CREATE,
            payload_hash="a" * 64,
            at=NOW + timedelta(seconds=2),
        )


@pytest.mark.parametrize(
    ("overrides", "error_type"),
    [
        ({"decision": "reject"}, ApprovalRequiredError),
        ({"expires_at": NOW + timedelta(milliseconds=500)}, ApprovalRequiredError),
        ({"approver_user_id": "other"}, PermissionDeniedError),
        ({"thread_id": "other"}, PermissionDeniedError),
        ({"action": OrderAction.CANCEL}, ConflictError),
        ({"payload_hash": "b" * 64}, ConflictError),
    ],
)
def test_grant_fails_closed_for_reject_expiry_or_binding_mismatch(
    overrides: dict[str, object], error_type: type[Exception]
) -> None:
    with pytest.raises(error_type):
        grant(**overrides).authorize_and_consume(
            operation_id="operation-1",
            user_id="user-1",
            thread_id="thread-1",
            action=OrderAction.CREATE,
            payload_hash="a" * 64,
            at=NOW + timedelta(seconds=1),
        )
