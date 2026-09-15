import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from langchain_core.messages import HumanMessage

from agent.context import ProcurementContext
from agent.model_factory import create_chat_model
from agent.subagents.analyst_schemas import AnalysisRequest
from agent.subagents.procurement_analyst import create_analyst_agent
from agent.tools.procurement_read import create_procurement_read_tools
from mcp_server.schemas import ToolEnvelope
from procurepilot.business.enums import Currency, Unit
from procurepilot.config import Settings

pytestmark = pytest.mark.live_model


@pytest.mark.asyncio
async def test_configured_model_can_answer_minimal_request() -> None:
    if os.environ.get("RUN_LIVE_MODEL_TESTS") != "1":
        pytest.skip("set RUN_LIVE_MODEL_TESTS=1 to allow a real model request")

    model = create_chat_model(Settings())
    response = await model.ainvoke([HumanMessage(content="Reply with exactly: OK")])

    assert response.text.strip() == "OK"


@pytest.mark.asyncio
async def test_configured_model_finishes_analysis_after_successful_quote() -> None:
    if os.environ.get("RUN_LIVE_MODEL_TESTS") != "1":
        pytest.skip("set RUN_LIVE_MODEL_TESTS=1 to allow a real model request")

    now = datetime.now(UTC)
    quote = {
        "quotation_id": "quote-live-1",
        "supplier_id": "supplier-live-1",
        "part_id": "part-live-1",
        "unit_price": "12.50",
        "currency": "CNY",
        "minimum_order_quantity": "10",
        "unit": "piece",
        "lead_time_days": 7,
        "source": "live-model-test",
        "collected_at": now.isoformat(),
        "valid_from": (now - timedelta(days=1)).isoformat(),
        "valid_until": (now + timedelta(days=30)).isoformat(),
    }

    class QuoteGateway:
        async def call_tool(self, tool_name, arguments, context):
            del arguments
            data = [quote] if tool_name == "quotation_query" else []
            return ToolEnvelope(ok=True, data=data, error=None, trace_id=context.trace_id)

    settings = Settings(model_call_limit=6, tool_call_limit=12)
    analyst = await create_analyst_agent(
        create_chat_model(settings),
        create_procurement_read_tools(QuoteGateway()),
        model_call_limit=6,
        tool_call_limit=12,
    )
    outcome = await analyst.analyze(
        AnalysisRequest(
            part_id="part-live-1",
            quantity=Decimal("100"),
            unit=Unit.PIECE,
            currency=Currency.CNY,
            valid_at=now,
        ),
        ProcurementContext(
            user_id="live-model-user",
            roles=frozenset({"procurement_reader"}),
            trace_id="live-model-trace",
        ),
    )

    assert outcome.ok is True
    assert outcome.data is not None
    assert len(outcome.data.candidates) == 1
