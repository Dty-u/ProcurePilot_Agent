"""附带显式排除依据的供应商比价服务。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from procurepilot.business.entities import Supplier, SupplierQuotation
from procurepilot.business.enums import SupplierStatus, Unit
from procurepilot.business.errors import EntityNotFoundError
from procurepilot.business.query_models import ComparisonRequest, QuotationSearchCriteria
from procurepilot.business.repositories import UnitOfWork


@dataclass(frozen=True, slots=True)
class ComparisonCandidate:
    supplier: Supplier
    quotation: SupplierQuotation


@dataclass(frozen=True, slots=True)
class ExcludedQuotation:
    quotation_id: str
    supplier_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    candidates: tuple[ComparisonCandidate, ...]
    excluded: tuple[ExcludedQuotation, ...]


class ComparisonService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def compare_suppliers(
        self,
        request: ComparisonRequest,
        at: datetime,
    ) -> ComparisonResult:
        async with self._uow_factory() as uow:
            part = await uow.parts.get_by_id(request.part_id)
            if part is None:
                raise EntityNotFoundError(f"part not found: {request.part_id}")
            part.ensure_procurement_eligible()
            quotations = await uow.quotations.search(
                QuotationSearchCriteria(part_id=request.part_id)
            )

            candidates: list[ComparisonCandidate] = []
            excluded: list[ExcludedQuotation] = []
            for quotation in quotations:
                reason = await self._exclusion_reason(uow, quotation, request, at, part.unit)
                if reason is not None:
                    excluded.append(
                        ExcludedQuotation(
                            quotation_id=quotation.quotation_id,
                            supplier_id=quotation.supplier_id,
                            reason=reason,
                        )
                    )
                    continue
                supplier = await uow.suppliers.get_by_id(quotation.supplier_id)
                if supplier is None:
                    excluded.append(
                        ExcludedQuotation(
                            quotation.quotation_id,
                            quotation.supplier_id,
                            "supplier_not_found",
                        )
                    )
                    continue
                candidates.append(ComparisonCandidate(supplier, quotation))

        candidates.sort(
            key=lambda candidate: (
                candidate.quotation.unit_price.amount,
                candidate.quotation.lead_time_days,
            )
        )
        return ComparisonResult(tuple(candidates), tuple(excluded))

    @staticmethod
    async def _exclusion_reason(
        uow: UnitOfWork,
        quotation: SupplierQuotation,
        request: ComparisonRequest,
        at: datetime,
        part_unit: Unit,
    ) -> str | None:
        if not quotation.is_valid_at(at):
            return "quotation_expired"
        if quotation.unit_price.currency is not request.currency:
            return "currency_mismatch"
        if quotation.minimum_order_quantity.unit is not part_unit:
            return "unit_mismatch"
        if not quotation.supports_quantity(request.quantity):
            return "minimum_order_quantity_not_met"
        supplier = await uow.suppliers.get_by_id(quotation.supplier_id)
        if supplier is None:
            return "supplier_not_found"
        if supplier.status is not SupplierStatus.ACTIVE:
            return "supplier_inactive"
        return None
