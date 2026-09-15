from collections.abc import Callable
from typing import cast

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from procurepilot.business.errors import ConflictError, InfrastructureError
from procurepilot.infrastructure.mysql_uow import MySQLUnitOfWork


class FakeSession:
    def __init__(self, commit_error: Exception | None = None) -> None:
        self.commit_error = commit_error
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


def factory_for(session: FakeSession) -> Callable[[], AsyncSession]:
    return cast(Callable[[], AsyncSession], lambda: session)


@pytest.mark.asyncio
async def test_integrity_error_is_mapped_without_sql_or_dsn_details() -> None:
    original = IntegrityError("INSERT INTO secret", {"password": "hidden"}, Exception("1062"))
    session = FakeSession(original)
    uow = MySQLUnitOfWork(factory_for(session))

    async with uow:
        with pytest.raises(ConflictError) as captured:
            await uow.commit()

    assert "INSERT" not in str(captured.value)
    assert "password" not in str(captured.value)
    assert session.rolled_back


@pytest.mark.asyncio
async def test_database_failure_is_mapped_to_infrastructure_error() -> None:
    original = OperationalError("SELECT secret", {}, Exception("offline"))
    session = FakeSession(original)
    uow = MySQLUnitOfWork(factory_for(session))

    async with uow:
        with pytest.raises(InfrastructureError, match="database transaction failed"):
            await uow.commit()

    assert session.rolled_back


@pytest.mark.asyncio
async def test_exit_without_commit_rolls_back_and_closes_session() -> None:
    session = FakeSession()

    async with MySQLUnitOfWork(factory_for(session)):
        pass

    assert session.rolled_back
    assert session.closed


@pytest.mark.asyncio
async def test_repository_sqlalchemy_error_is_mapped_at_uow_boundary() -> None:
    session = FakeSession()
    uow = MySQLUnitOfWork(factory_for(session))

    with pytest.raises(InfrastructureError, match="database operation failed"):
        async with uow:
            raise OperationalError("SELECT secret", {}, Exception("offline"))

    assert session.rolled_back
    assert session.closed


@pytest.mark.asyncio
async def test_repository_integrity_error_is_mapped_at_uow_boundary() -> None:
    session = FakeSession()
    uow = MySQLUnitOfWork(factory_for(session))

    with pytest.raises(ConflictError, match="database uniqueness"):
        async with uow:
            raise IntegrityError("INSERT secret", {}, Exception("duplicate"))

    assert session.rolled_back
