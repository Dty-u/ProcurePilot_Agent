"""采购分析的已校验输入与输出模型。"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from procurepilot.business.enums import Currency, Unit


class AnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AnalysisRequest(AnalysisModel):
    part_id: str = Field(min_length=1, max_length=128)
    quantity: Decimal = Field(gt=0)
    unit: Unit
    currency: Currency
    valid_at: datetime

    @field_validator("valid_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("valid_at must be timezone-aware")
        return value


class SupplierCandidate(AnalysisModel):
    supplier_id: str = Field(min_length=1, max_length=128)
    quotation_id: str = Field(min_length=1, max_length=128)
    unit_price: Decimal = Field(gt=0)
    currency: Currency
    unit: Unit
    minimum_order_quantity: Decimal = Field(gt=0)
    lead_time_days: int = Field(ge=0)
    eligible: bool = True
    exclusion_reasons: list[str] = Field(default_factory=list)


class EvidenceItem(AnalysisModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    evidence_type: Literal["internal", "external"]
    source: str = Field(min_length=1, max_length=500)
    url: HttpUrl | None = None
    collected_at: datetime
    validity: str = Field(min_length=1, max_length=1000)
    supplier_id: str | None = Field(default=None, min_length=1, max_length=128)
    quotation_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("collected_at")
    @classmethod
    def require_aware_collection_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_external_url(self) -> Self:
        if self.evidence_type == "external" and self.url is None:
            raise ValueError("external evidence requires url")
        return self


class ArtifactReference(AnalysisModel):
    artifact_id: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=1000)
    media_type: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)


class AnalysisResult(AnalysisModel):
    summary: str = Field(min_length=1)
    candidates: list[SupplierCandidate]
    recommendation: str | None
    evidence: list[EvidenceItem]
    risks: list[str]
    limitations: list[str]
    artifacts: list[ArtifactReference]

    @model_validator(mode="after")
    def validate_no_candidate_result(self) -> Self:
        if not self.candidates:
            if self.recommendation is not None:
                raise ValueError("recommendation must be empty without candidates")
            if not self.limitations:
                raise ValueError("limitations are required without candidates")
        return self


AnalysisErrorCode = Literal[
    "INVALID_MODEL_OUTPUT",
    "UNGROUNDED_RESULT",
    "CALL_LIMIT_EXCEEDED",
    "EXECUTION_ERROR",
]


class AnalysisError(AnalysisModel):
    code: AnalysisErrorCode
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False


class AnalysisOutcome(AnalysisModel):
    ok: bool
    data: AnalysisResult | None
    error: AnalysisError | None
    trace_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.ok and (self.data is None or self.error is not None):
            raise ValueError("successful analysis requires data and forbids error")
        if not self.ok and (self.data is not None or self.error is None):
            raise ValueError("failed analysis requires error and forbids data")
        return self
