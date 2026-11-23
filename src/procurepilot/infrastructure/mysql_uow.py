"""基于 SQLAlchemy 的工作单元，带稳定的错误映射。"""

from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from procurepilot.business.errors import ConflictError, InfrastructureError
from procurepilot.infrastructure.mysql_repositories import (
    MySQLApprovalRepository,
    MySQLAuditRepository,
    MySQLInventoryRepository,
    MySQLOrderOperationRepository,
    MySQLOrderRepository,
    MySQLPartRepository,
    MySQLQuotationRepository,
    MySQLSupplierRepository,
)


class MySQLUnitOfWork:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        session = self._session_factory()
        self._session = session
        self.suppliers = MySQLSupplierRepository(session)
        self.parts = MySQLPartRepository(session)
        self.quotations = MySQLQuotationRepository(session)
        self.inventory = MySQLInventoryRepository(session)
        self.orders = MySQLOrderRepository(session)
        self.approvals = MySQLApprovalRepository(session)
        self.operations = MySQLOrderOperationRepository(session)
        self.audits = MySQLAuditRepository(session)
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is not None or not self._committed:
                await session.rollback()
        finally:
            await session.close()
            self._session = None
        if isinstance(exc, IntegrityError):
            raise ConflictError("database uniqueness or reference conflict") from None
        if isinstance(exc, SQLAlchemyError):
            raise InfrastructureError("database operation failed") from None

    async def commit(self) -> None:
        session = self._require_session()
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            self._committed = False
            raise ConflictError("database uniqueness or reference conflict") from None
        except SQLAlchemyError:
            await session.rollback()
            self._committed = False
            raise InfrastructureError("database transaction failed") from None
        self._committed = True

    async def rollback(self) -> None:
        await self._require_session().rollback()
        self._committed = False

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Unit of work is not active")
        return self._session
