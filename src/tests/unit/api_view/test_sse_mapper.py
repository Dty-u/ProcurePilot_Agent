import json

import pytest
from langchain_core.messages import AIMessageChunk, ToolMessage

from api_view.sse import SSEMapper, encode_sse


@pytest.mark.asyncio
async def test_values_interrupt_has_priority_and_finishes_stream() -> None:
    async def chunks():
        yield "values", {"__interrupt__": [{"id": "i-1", "value": {"action": "review"}}]}
        yield "messages", {"type": "token", "text": "must-not-leak"}

    events = [item async for item in SSEMapper("thread-1").map(chunks())]

    assert [item.event for item in events] == ["interrupt", "done"]
    assert events[-1].payload == {"interrupted": True}


@pytest.mark.asyncio
async def test_tool_events_are_redacted_and_bounded() -> None:
    async def chunks():
        yield "messages", {
            "type": "tool_result",
            "tool_name": "quotation_query",
            "content": "api_key=secret " + "x" * 5000,
        }

    events = [item async for item in SSEMapper("thread-1", max_payload_chars=200).map(chunks())]

    assert events[0].event == "tool_result"
    dumped = json.dumps(events[0].payload)
    assert "secret" not in dumped
    assert len(dumped) < 500
    assert encode_sse(events[0]).startswith("id: ")


@pytest.mark.asyncio
async def test_real_langchain_chunks_map_to_tool_lifecycle() -> None:
    async def chunks():
        yield "messages", AIMessageChunk(content="查询中", tool_call_chunks=[
            {"name": "quotation_query", "args": '{"part_id":"P-1"}', "id": "c-1", "index": 0}
        ])
        yield "messages", ToolMessage(
            content='{"ok":true}', name="quotation_query", tool_call_id="c-1"
        )

    events = [item async for item in SSEMapper("thread-1").map(chunks())]

    assert [item.event for item in events] == [
        "token",
        "tool_start",
        "tool_args",
        "tool_result",
        "tool_end",
        "done",
    ]
