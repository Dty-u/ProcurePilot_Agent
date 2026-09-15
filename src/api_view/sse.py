"""LangGraph 流到稳定 SSE 信封的转换。"""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from api_view.message_repository import redact_message_content

SSEEvent = Literal[
    "token",
    "tool_start",
    "tool_args",
    "tool_result",
    "tool_end",
    "interrupt",
    "done",
]


class SSEEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: Literal["1"] = "1"
    event_id: str
    event: SSEEvent
    thread_id: str
    timestamp: datetime
    source: str
    payload: dict[str, Any]


class SSEMapper:
    def __init__(self, thread_id: str, *, max_payload_chars: int = 2_000) -> None:
        self._thread_id = thread_id
        self._max_payload_chars = max_payload_chars
        self._started_tools: set[str] = set()

    async def map(
        self,
        chunks: AsyncIterable[tuple[str, Any]],
    ) -> AsyncIterator[SSEEnvelope]:
        async for mode, chunk in chunks:
            if mode == "values":
                interrupts = chunk.get("__interrupt__") if isinstance(chunk, dict) else None
                if interrupts:
                    yield self._event("interrupt", {"interrupts": _safe(interrupts, self._max_payload_chars)})
                    yield self._event("done", {"interrupted": True})
                    return
                continue
            for name, payload in self._message_events(chunk):
                yield self._event(name, _safe(payload, self._max_payload_chars))
        yield self._event("done", {"interrupted": False})

    def error(self, code: str = "stream_failed") -> SSEEnvelope:
        return self._event("done", {"interrupted": False, "ok": False, "error": code})

    def _event(self, event: SSEEvent, payload: dict[str, Any]) -> SSEEnvelope:
        return SSEEnvelope(
            event_id=str(uuid4()),
            event=event,
            thread_id=self._thread_id,
            timestamp=datetime.now(UTC),
            source="procurepilot-agent",
            payload=payload,
        )

    def _message_events(self, chunk: Any) -> list[tuple[SSEEvent, dict[str, Any]]]:
        if isinstance(chunk, tuple) and chunk:
            chunk = chunk[0]
        if isinstance(chunk, dict) and chunk.get("type") in {
            "token",
            "tool_start",
            "tool_args",
            "tool_result",
            "tool_end",
        }:
            return [
                (chunk["type"], {key: value for key, value in chunk.items() if key != "type"})
            ]

        content = getattr(chunk, "content", None)
        if type(chunk).__name__ == "AIMessageChunk":
            events: list[tuple[SSEEvent, dict[str, Any]]] = []
            if isinstance(content, str) and content:
                events.append(("token", {"text": content}))
            for call in getattr(chunk, "tool_call_chunks", []) or []:
                call_id = str(call.get("id") or call.get("index") or "unknown")
                tool_name = call.get("name")
                if tool_name and call_id not in self._started_tools:
                    self._started_tools.add(call_id)
                    events.append(
                        ("tool_start", {"tool_call_id": call_id, "tool_name": tool_name})
                    )
                if call.get("args"):
                    events.append(
                        (
                            "tool_args",
                            {
                                "tool_call_id": call_id,
                                "tool_name": tool_name,
                                "args": call["args"],
                            },
                        )
                    )
            return events
        if getattr(chunk, "type", None) == "tool" or type(chunk).__name__ == "ToolMessage":
            call_id = str(getattr(chunk, "tool_call_id", "unknown"))
            common = {
                "tool_call_id": call_id,
                "tool_name": getattr(chunk, "name", None),
            }
            return [
                (
                    "tool_result",
                    {
                        **common,
                        "content": content if isinstance(content, str) else str(content),
                    },
                ),
                ("tool_end", {**common, "status": getattr(chunk, "status", "success")}),
            ]
        return []


def _safe(value: Any, limit: int) -> Any:
    if isinstance(value, str):
        redacted = redact_message_content(value)
        return redacted if len(redacted) <= limit else redacted[:limit] + "…[TRUNCATED]"
    if isinstance(value, dict):
        return {str(key): _safe(item, limit) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item, limit) for item in value]
    if hasattr(value, "value"):
        return _safe(value.value, limit)
    return value if isinstance(value, (int, float, bool)) or value is None else str(value)


def encode_sse(envelope: SSEEnvelope) -> str:
    data = envelope.model_dump_json()
    return f"id: {envelope.event_id}\nevent: {envelope.event}\ndata: {data}\n\n"
