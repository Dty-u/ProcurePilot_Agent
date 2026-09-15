"""Restricted procurement analyst construction and output grounding."""

import json
from decimal import Decimal
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import BaseTool

from agent.context import ProcurementContext
from agent.middlewares import create_runtime_middleware
from agent.subagents.analyst_prompt import ANALYST_SYSTEM_PROMPT
from agent.subagents.analyst_schemas import (
    AnalysisError,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisResult,
    SupplierCandidate,
)

EXPECTED_TOOL_NAMES = frozenset(
    {
        "supplier_query",
        "part_query",
        "part_by_supplier",
        "quotation_query",
        "inventory_warning",
        "order_search_details",
    }
)


class ProcurementAnalyst:
    """Small safety wrapper around the compiled LangGraph Agent."""

    def __init__(self, graph: Any, tool_names: tuple[str, ...]) -> None:
        self._graph = graph
        self.tool_names = tool_names
        self.framework = "deepagents"

    @property
    def graph(self) -> Any:
        return self._graph

    async def analyze(
        self,
        request: AnalysisRequest,
        context: ProcurementContext,
    ) -> AnalysisOutcome:
        if not isinstance(context, ProcurementContext):
            raise PermissionError("trusted ProcurementContext is required")
        try:
            state = await self._graph.ainvoke(
                {"messages": [HumanMessage(content=request.model_dump_json())]},
                context=context,
            )
        except (ModelCallLimitExceededError, ToolCallLimitExceededError):
            return self._failure(
                context,
                "CALL_LIMIT_EXCEEDED",
                "Analysis stopped because its configured call limit was reached",
            )
        except Exception:
            return self._failure(
                context,
                "EXECUTION_ERROR",
                "Analysis execution failed",
                retryable=True,
            )

        raw_result = state.get("structured_response")
        try:
            result = AnalysisResult.model_validate(raw_result)
        except Exception:
            return self._failure(
                context,
                "INVALID_MODEL_OUTPUT",
                "The model did not return a valid analysis structure",
            )

        grounding_error = _validate_grounding(result, state.get("messages", []))
        if grounding_error is not None:
            return self._failure(
                context,
                "UNGROUNDED_RESULT",
                grounding_error,
            )
        return AnalysisOutcome(
            ok=True,
            data=result,
            error=None,
            trace_id=context.trace_id,
        )

    @staticmethod
    def _failure(
        context: ProcurementContext,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> AnalysisOutcome:
        return AnalysisOutcome(
            ok=False,
            data=None,
            error=AnalysisError.model_validate(
                {"code": code, "message": message, "retryable": retryable}
            ),
            trace_id=context.trace_id,
        )


def _quotation_evidence(messages: list[Any]) -> tuple[bool, dict[tuple[str, str], dict[str, Any]]]:
    queried = False
    quotations: dict[tuple[str, str], dict[str, Any]] = {}
    for message in messages:
        if not isinstance(message, ToolMessage) or message.name != "quotation_query":
            continue
        content = message.content
        if not isinstance(content, str):
            continue
        try:
            envelope = json.loads(content)
        except (TypeError, ValueError):
            continue
        if not isinstance(envelope, dict) or envelope.get("ok") is not True:
            continue
        queried = True
        data = envelope.get("data")
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            supplier_id = item.get("supplier_id")
            quotation_id = item.get("quotation_id")
            if isinstance(supplier_id, str) and isinstance(quotation_id, str):
                quotations[(supplier_id, quotation_id)] = item
    return queried, quotations


def _candidate_matches_quote(candidate: SupplierCandidate, quote: dict[str, Any]) -> bool:
    try:
        return (
            candidate.unit_price == Decimal(str(quote["unit_price"]))
            and candidate.currency.value == quote["currency"]
            and candidate.unit.value == quote["unit"]
            and candidate.minimum_order_quantity
            == Decimal(str(quote["minimum_order_quantity"]))
            and candidate.lead_time_days == quote["lead_time_days"]
        )
    except (KeyError, ValueError):
        return False


def _validate_grounding(result: AnalysisResult, messages: list[Any]) -> str | None:
    queried, quotations = _quotation_evidence(messages)
    if not queried:
        return "No successful quotation evidence was available"
    if quotations and not result.candidates:
        return "Valid quotation evidence was omitted from the candidate list"
    if any(item.evidence_type == "external" for item in result.evidence):
        return "External evidence is unsupported by the available read tools"

    evidence_keys = {
        (item.supplier_id, item.quotation_id)
        for item in result.evidence
        if item.supplier_id is not None and item.quotation_id is not None
    }
    for candidate in result.candidates:
        key = (candidate.supplier_id, candidate.quotation_id)
        quote = quotations.get(key)
        if quote is None or not _candidate_matches_quote(candidate, quote):
            return "A candidate does not match successful quotation evidence"
        if key not in evidence_keys:
            return "A candidate is missing linked evidence"
    return None


async def create_analyst_agent(
    model: BaseChatModel,
    tools: list[BaseTool],
    *,
    model_call_limit: int = 50,
    tool_call_limit: int = 200,
    backend: Any = StateBackend,
    skills: list[str] | None = None,
) -> ProcurementAnalyst:
    """Build the analyst through the pinned DeepAgents factory."""

    tool_names = tuple(sorted(tool.name for tool in tools))
    if set(tool_names) != EXPECTED_TOOL_NAMES or len(tool_names) != len(EXPECTED_TOOL_NAMES):
        raise ValueError("analyst requires exactly the six approved read-only tools")
    graph = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=ANALYST_SYSTEM_PROMPT,
        response_format=ToolStrategy(AnalysisResult),
        context_schema=ProcurementContext,
        middleware=create_runtime_middleware(
            model_call_limit=model_call_limit,
            tool_call_limit=tool_call_limit,
            include_context_injection=False,
        ),
        subagents=[],
        skills=skills,
        memory=None,
        checkpointer=False,
        store=None,
        backend=backend,
        interrupt_on={},
        debug=False,
        name="procurement-analyst",
        cache=None,
    )
    return ProcurementAnalyst(graph, tool_names)
