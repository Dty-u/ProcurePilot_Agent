import pytest

from agent.toolsets import (
    ANALYST_TOOL_NAMES,
    MAIN_TOOL_NAMES,
    ORDER_TOOL_NAMES,
    validate_tool_names,
)


def test_agent_toolsets_enforce_least_privilege() -> None:
    assert MAIN_TOOL_NAMES.isdisjoint({"order_create", "order_update", "order_cancel"})
    assert ANALYST_TOOL_NAMES.isdisjoint({"order_create", "order_update", "order_cancel"})
    assert {"order_create", "order_update", "order_cancel"} <= ORDER_TOOL_NAMES
    assert ANALYST_TOOL_NAMES == {
        "supplier_query",
        "part_query",
        "part_by_supplier",
        "quotation_query",
        "inventory_warning",
        "order_search_details",
    }


def test_default_tool_inheritance_is_rejected() -> None:
    with pytest.raises(ValueError, match="exactly"):
        validate_tool_names("procurement-analyst", ["supplier_query"])
