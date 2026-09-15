from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from procurepilot.business.enums import Currency, SupplierStatus, Unit
from procurepilot.business.query_models import (
    ComparisonRequest,
    PartSearchCriteria,
    QuotationSearchCriteria,
    SupplierSearchCriteria,
)
from procurepilot.business.repositories import ApprovalRepository, SupplierRepository, UnitOfWork
from procurepilot.business.value_objects import PositiveQuantity


def test_supplier_search_criteria_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SupplierSearchCriteria(keyword="fastener", sql="drop table")  # type: ignore[call-arg]

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_search_criteria_validate_limits_and_enum_values() -> None:
    with pytest.raises(ValidationError):
        SupplierSearchCriteria(limit=0)
    with pytest.raises(ValidationError):
        PartSearchCriteria(status="enabled")  # type: ignore[arg-type]

    criteria = SupplierSearchCriteria(status=SupplierStatus.ACTIVE, limit=20)
    assert criteria.status is SupplierStatus.ACTIVE


def test_quotation_search_uses_explicit_typed_fields() -> None:
    criteria = QuotationSearchCriteria(
        part_id="part-1",
        currency=Currency.CNY,
        unit=Unit.PIECE,
        quantity=PositiveQuantity(Decimal("100"), Unit.PIECE),
    )

    assert criteria.part_id == "part-1"
    assert criteria.quantity.amount == Decimal("100")


def test_comparison_request_requires_part_quantity_and_currency() -> None:
    request = ComparisonRequest(
        part_id="part-1",
        quantity=PositiveQuantity(Decimal("500"), Unit.PIECE),
        currency=Currency.CNY,
    )

    assert request.currency is Currency.CNY


def test_repository_protocol_requires_declared_async_methods() -> None:
    class CompleteSupplierRepository:
        async def get_by_id(self, supplier_id: str) -> object | None:
            return None

        async def search(self, criteria: SupplierSearchCriteria) -> list[object]:
            return []

        async def add(self, supplier: object) -> None:
            return None

    class IncompleteSupplierRepository:
        pass

    assert isinstance(CompleteSupplierRepository(), SupplierRepository)
    assert not isinstance(IncompleteSupplierRepository(), SupplierRepository)


def test_unit_of_work_protocol_requires_transaction_boundary() -> None:
    class IncompleteUnitOfWork:
        async def commit(self) -> None:
            return None

    assert not isinstance(IncompleteUnitOfWork(), UnitOfWork)


def test_approval_repository_requires_atomic_consumption_operation() -> None:
    class CompleteApprovalRepository:
        async def is_approved(self, *, operation_id: str, actor_id: str) -> bool:
            return True

        async def consume(self, *, operation_id: str, actor_id: str, at: datetime) -> None:
            return None

    assert isinstance(CompleteApprovalRepository(), ApprovalRepository)
