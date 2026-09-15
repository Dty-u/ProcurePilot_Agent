import pytest

from agent.subagents.loader import load_subagent_configs, resolve_subagent_tools
from agent.toolsets import ANALYST_TOOL_NAMES, ORDER_TOOL_NAMES


def test_repository_subagent_configs_load_and_enforce_declared_toolsets() -> None:
    configs = load_subagent_configs()

    analyst = configs["procurement-analyst"]
    order = configs["procurement-order"]

    assert analyst.tool_names == tuple(sorted(ANALYST_TOOL_NAMES))
    assert order.tool_names == tuple(sorted(ORDER_TOOL_NAMES))
    assert resolve_subagent_tools(analyst, [*ANALYST_TOOL_NAMES, "order_create"]) == list(
        analyst.tool_names
    )
    assert resolve_subagent_tools(order, [*ORDER_TOOL_NAMES, "inventory_warning"]) == list(
        order.tool_names
    )


def test_subagent_tool_resolution_rejects_a_missing_declared_tool() -> None:
    analyst = load_subagent_configs()["procurement-analyst"]

    with pytest.raises(ValueError, match="missing approved tools"):
        resolve_subagent_tools(analyst, ["supplier_query"])
