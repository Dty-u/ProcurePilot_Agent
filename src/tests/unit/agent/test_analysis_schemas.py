from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agent.subagents.analyst_schemas import (
    AnalysisRequest,
    AnalysisResult,
    EvidenceItem,
    SupplierCandidate,
)
from procurepilot.business.enums import Currency, Unit

NOW = datetime(2026, 9, 9, tzinfo=UTC)


def test_analysis_request_requires_procurement_scope() -> None:
    request = AnalysisRequest(
        part_id="part-1",
        quantity=Decimal("100"),
        unit=Unit.PIECE,
        currency=Currency.CNY,
        valid_at=NOW,
    )

    assert request.quantity == Decimal("100")
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate(
            {
                "part_id": "part-1",
                "quantity": "100",
                "unit": "piece",
                "currency": "CNY",
                "valid_at": NOW.isoformat(),
                "user_id": "spoofed",
            }
        )


def test_candidate_requires_supplier_and_quotation_ids() -> None:
    with pytest.raises(ValidationError):
        SupplierCandidate.model_validate(
            {
                "supplier_id": "",
                "quotation_id": "quote-1",
                "unit_price": "12.50",
                "currency": "CNY",
                "unit": "piece",
                "minimum_order_quantity": "1",
                "lead_time_days": 3,
            }
        )


def test_external_evidence_requires_url_collection_time_and_validity() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="ev-1",
            evidence_type="external",
            source="supplier website",
            url=None,
            collected_at=NOW,
            validity="valid on collection date",
        )


def test_no_candidates_forces_empty_recommendation_and_limitations() -> None:
    result = AnalysisResult(
        summary="No valid quotation was found.",
        candidates=[],
        recommendation=None,
        evidence=[],
        risks=["No price comparison is possible."],
        limitations=["Quotation evidence is unavailable."],
        artifacts=[],
    )

    assert result.recommendation is None
    with pytest.raises(ValidationError):
        AnalysisResult(
            summary="No data.",
            candidates=[],
            recommendation="Choose supplier-1.",
            evidence=[],
            risks=[],
            limitations=[],
            artifacts=[],
        )
