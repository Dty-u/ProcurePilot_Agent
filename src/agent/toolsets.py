"""Auditable least-privilege tool manifests for every procurement agent."""

from collections.abc import Sequence

from langchain_core.tools import BaseTool

MAIN_TOOL_NAMES: frozenset[str] = frozenset()
ANALYST_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "supplier_query",
        "part_query",
        "part_by_supplier",
        "quotation_query",
        "inventory_warning",
        "order_search_details",
    }
)
ORDER_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "supplier_query",
        "part_query",
        "quotation_query",
        "order_search_details",
        "request_order_info",
        "order_create",
        "order_update",
        "order_cancel",
    }
)

_EXPECTED = {
    "main": MAIN_TOOL_NAMES,
    "procurement-analyst": ANALYST_TOOL_NAMES,
    "procurement-order": ORDER_TOOL_NAMES,
}


def validate_tool_names(agent_name: str, tools: Sequence[BaseTool | str]) -> tuple[str, ...]:
    expected = _EXPECTED[agent_name]
    names = tuple(sorted(item if isinstance(item, str) else item.name for item in tools))
    if set(names) != expected or len(names) != len(expected):
        raise ValueError(f"{agent_name} requires exactly its approved tool set")
    return names
