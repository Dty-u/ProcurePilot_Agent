import inspect
import re
from typing import Any, cast

from agent.prompts import MAIN_SYSTEM_PROMPT
from agent.subagents.analyst_prompt import ANALYST_SYSTEM_PROMPT
from agent.subagents.loader import load_subagent_configs
from agent.subagents.order_info import OrderDraft, build_info_request
from agent.subagents.order_prompt import ORDER_SYSTEM_PROMPT
from agent.subagents.procurement_order import create_order_subagent
from agent.tools.procurement_read import (
    ProcurementReadGateway,
    create_procurement_read_tools,
)
from mcp_server.server_main import ServiceContainer, create_mcp_server
from procurepilot.business.enums import OrderAction
from procurepilot.config import Settings


def _assert_primarily_chinese(text: str) -> None:
    chinese_character_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_character_count = len(re.findall(r"[A-Za-z]", text))

    assert chinese_character_count > 0
    assert chinese_character_count > latin_character_count


def test_all_model_facing_prompts_and_descriptions_are_chinese() -> None:
    configs = load_subagent_configs()
    default_order_description = inspect.signature(create_order_subagent).parameters[
        "description"
    ].default
    read_tools = create_procurement_read_tools(cast(ProcurementReadGateway, object()))
    settings = Settings.model_construct(request_timeout_seconds=5.0)
    container = ServiceContainer(
        supplier_service=cast(Any, object()),
        part_service=cast(Any, object()),
        quotation_service=cast(Any, object()),
        inventory_service=cast(Any, object()),
        order_query_service=cast(Any, object()),
        caller_context_provider=cast(Any, object()),
    )
    mcp_server = create_mcp_server(settings, container)
    info_request = build_info_request(OrderDraft(action=OrderAction.CREATE))

    model_facing_texts = [
        MAIN_SYSTEM_PROMPT,
        ANALYST_SYSTEM_PROMPT,
        ORDER_SYSTEM_PROMPT,
        configs["procurement-analyst"].description,
        configs["procurement-order"].description,
        default_order_description,
        mcp_server.instructions,
        info_request.safety_notice,
        *(tool.description for tool in read_tools),
    ]

    for text in model_facing_texts:
        _assert_primarily_chinese(text)
