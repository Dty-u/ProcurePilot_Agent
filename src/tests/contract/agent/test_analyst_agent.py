from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent.context import ProcurementContext
from agent.subagents.analyst_schemas import (
    AnalysisRequest,
    AnalysisResult,
    EvidenceItem,
    SupplierCandidate,
)
from agent.subagents.procurement_analyst import create_analyst_agent
from agent.tools.procurement_read import create_procurement_read_tools
from mcp_server.schemas import ToolEnvelope, ToolError
from procurepilot.business.enums import Currency, Unit

NOW = datetime(2026, 9, 9, tzinfo=UTC)
REQUEST = AnalysisRequest(
    part_id="part-1",
    quantity=Decimal("100"),
    unit=Unit.PIECE,
    currency=Currency.CNY,
    valid_at=NOW,
)
CONTEXT = ProcurementContext(
    user_id="user-1",
    roles=frozenset({"procurement_reader"}),
    trace_id="trace-agent-1",
)
QUOTE = {
    "quotation_id": "quote-1",
    "supplier_id": "supplier-1",
    "part_id": "part-1",
    "unit_price": "12.50",
    "currency": "CNY",
    "minimum_order_quantity": "10",
    "unit": "piece",
    "lead_time_days": 3,
    "source": "erp",
    "collected_at": NOW.isoformat(),
    "valid_from": (NOW - timedelta(days=1)).isoformat(),
    "valid_until": (NOW + timedelta(days=1)).isoformat(),
}


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage]
    response_index: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-analyst-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        return self

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        response = self.responses[min(self.response_index, len(self.responses) - 1)]
        self.response_index += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


class QuoteGateway:
    def __init__(self, quote_envelope: ToolEnvelope[Any]) -> None:
        self.quote_envelope = quote_envelope

    async def call_tool(self, tool_name, arguments, context):
        if tool_name == "quotation_query":
            return self.quote_envelope
        return ToolEnvelope(ok=True, data=[], error=None, trace_id=context.trace_id)


def quotation_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "quotation_query",
                "args": {
                    "request": {
                        "part_id": "part-1",
                        "currency": "CNY",
                        "unit": "piece",
                        "quantity": "100",
                        "at": NOW.isoformat(),
                    }
                },
                "id": "quote-call-1",
                "type": "tool_call",
            }
        ],
    )


def structured_response(result: AnalysisResult) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "AnalysisResult",
                "args": result.model_dump(mode="json"),
                "id": "result-call-1",
                "type": "tool_call",
            }
        ],
    )


def valid_result() -> AnalysisResult:
    return AnalysisResult(
        summary="One valid quotation is available.",
        candidates=[
            SupplierCandidate(
                supplier_id="supplier-1",
                quotation_id="quote-1",
                unit_price=Decimal("12.50"),
                currency=Currency.CNY,
                unit=Unit.PIECE,
                minimum_order_quantity=Decimal("10"),
                lead_time_days=3,
            )
        ],
        recommendation="Consider supplier-1 based on the valid ERP quotation.",
        evidence=[
            EvidenceItem(
                evidence_id="quote-1",
                evidence_type="internal",
                source="erp",
                url=None,
                collected_at=NOW,
                validity="Valid for the requested date and quantity.",
                supplier_id="supplier-1",
                quotation_id="quote-1",
            )
        ],
        risks=["Single-source quotation."],
        limitations=[],
        artifacts=[],
    )


@pytest.mark.asyncio
async def test_valid_quote_forms_traceable_candidate() -> None:
    gateway = QuoteGateway(
        ToolEnvelope(ok=True, data=[QUOTE], error=None, trace_id=CONTEXT.trace_id)
    )
    tools = create_procurement_read_tools(gateway)
    analyst = await create_analyst_agent(
        ScriptedModel(responses=[quotation_call(), structured_response(valid_result())]), tools
    )

    outcome = await analyst.analyze(REQUEST, CONTEXT)

    assert analyst.framework == "deepagents"
    assert analyst.tool_names == (
        "inventory_warning",
        "order_search_details",
        "part_by_supplier",
        "part_query",
        "quotation_query",
        "supplier_query",
    )
    assert outcome.ok is True
    assert outcome.data is not None
    assert outcome.data.candidates[0].supplier_id == "supplier-1"
    assert outcome.data.candidates[0].quotation_id == "quote-1"


@pytest.mark.asyncio
async def test_no_quote_returns_evidence_limitation_without_recommendation() -> None:
    gateway = QuoteGateway(ToolEnvelope(ok=True, data=[], error=None, trace_id=CONTEXT.trace_id))
    no_data = AnalysisResult(
        summary="No valid quotations were found.",
        candidates=[],
        recommendation=None,
        evidence=[],
        risks=["Supplier comparison cannot be completed."],
        limitations=["No valid quotation evidence."],
        artifacts=[],
    )
    analyst = await create_analyst_agent(
        ScriptedModel(responses=[quotation_call(), structured_response(no_data)]),
        create_procurement_read_tools(gateway),
    )

    outcome = await analyst.analyze(REQUEST, CONTEXT)

    assert outcome.ok is True
    assert outcome.data is not None and outcome.data.recommendation is None
    assert outcome.data.limitations == ["No valid quotation evidence."]


@pytest.mark.asyncio
async def test_timeout_cannot_produce_hallucinated_recommendation() -> None:
    gateway = QuoteGateway(
        ToolEnvelope(
            ok=False,
            data=None,
            error=ToolError(
                code="DEPENDENCY_TIMEOUT", message="Dependency timeout", retryable=True
            ),
            trace_id=CONTEXT.trace_id,
        )
    )
    analyst = await create_analyst_agent(
        ScriptedModel(responses=[quotation_call(), structured_response(valid_result())]),
        create_procurement_read_tools(gateway),
    )

    outcome = await analyst.analyze(REQUEST, CONTEXT)

    assert outcome.ok is False
    assert outcome.data is None
    assert outcome.error is not None and outcome.error.code == "UNGROUNDED_RESULT"


@pytest.mark.asyncio
async def test_invalid_model_structure_returns_stable_failure() -> None:
    analyst = await create_analyst_agent(
        ScriptedModel(responses=[AIMessage(content="unvalidated recommendation")]),
        create_procurement_read_tools(
            QuoteGateway(ToolEnvelope(ok=True, data=[], error=None, trace_id=CONTEXT.trace_id))
        ),
    )

    outcome = await analyst.analyze(REQUEST, CONTEXT)

    assert outcome.ok is False
    assert outcome.error is not None and outcome.error.code == "INVALID_MODEL_OUTPUT"
    assert "unvalidated recommendation" not in outcome.error.message


@pytest.mark.asyncio
async def test_model_call_limit_stops_repeated_tool_loop() -> None:
    analyst = await create_analyst_agent(
        ScriptedModel(responses=[quotation_call()]),
        create_procurement_read_tools(
            QuoteGateway(ToolEnvelope(ok=True, data=[QUOTE], error=None, trace_id=CONTEXT.trace_id))
        ),
        model_call_limit=1,
        tool_call_limit=2,
    )

    outcome = await analyst.analyze(REQUEST, CONTEXT)

    assert outcome.ok is False
    assert outcome.error is not None and outcome.error.code == "CALL_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_tool_call_limit_stops_oversized_parallel_request() -> None:
    oversized_call = quotation_call()
    oversized_call.tool_calls.append(
        {
            "name": "supplier_query",
            "args": {"request": {}},
            "id": "supplier-call-2",
            "type": "tool_call",
        }
    )
    analyst = await create_analyst_agent(
        ScriptedModel(responses=[oversized_call]),
        create_procurement_read_tools(
            QuoteGateway(ToolEnvelope(ok=True, data=[QUOTE], error=None, trace_id=CONTEXT.trace_id))
        ),
        model_call_limit=5,
        tool_call_limit=1,
    )

    outcome = await analyst.analyze(REQUEST, CONTEXT)

    assert outcome.ok is False
    assert outcome.error is not None and outcome.error.code == "CALL_LIMIT_EXCEEDED"
