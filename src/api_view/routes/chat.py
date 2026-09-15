"""流式对话与一次性 HITL 恢复路由。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agent.context import ProcurementContext
from agent.resume_service import (
    DecisionResume,
    PendingInterrupt,
    SupplementResume,
    hash_parameter_summary,
)
from api_view.auth import HeaderAuthenticator
from api_view.container import ApplicationContainer
from api_view.message_repository import DisplayMessage
from api_view.schemas import ChatRequest, ResumeRequest
from api_view.sse import SSEMapper, encode_sse
from procurepilot.business.enums import OrderAction
from procurepilot.observability import audit_fields

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def _trusted_context(request: Request, thread_id: str) -> ProcurementContext:
    authenticator: HeaderAuthenticator = request.app.state.authenticator
    try:
        return authenticator.authenticate(
            request.headers,
            thread_id=thread_id,
            trace_id=f"trace-{uuid4()}",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc


async def _save_message(
    container: ApplicationContainer,
    context: ProcurementContext,
    role: Literal["user", "assistant"],
    content: str,
) -> None:
    await container.messages.add(
        context,
        DisplayMessage(
            thread_id=context.thread_id,
            message_id=f"msg-{uuid4()}",
            role=role,
            content=content,
            occurred_at=datetime.now(UTC),
            source="api",
        ),
    )


def _stream(
    request: Request,
    context: ProcurementContext,
    graph_input: Any,
    *,
    save_user_message: str | None = None,
) -> StreamingResponse:
    container: ApplicationContainer = request.app.state.container
    mapper = SSEMapper(context.thread_id)

    async def events() -> AsyncIterator[str]:
        assistant_parts: list[str] = []
        try:
            await container.persistence.threads.claim(context)
            if save_user_message is not None:
                await _save_message(container, context, "user", save_user_message)
            async with container.open_agent(context) as agent:
                chunks = agent.graph.astream(
                    graph_input,
                    config={"configurable": {"thread_id": context.thread_id}},
                    context=context,
                    stream_mode=["messages", "values"],
                )

                async def registered_chunks() -> AsyncIterator[tuple[str, Any]]:
                    async for mode, chunk in chunks:
                        if mode == "values":
                            await _register_interrupts(container, context, chunk)
                        yield mode, chunk

                async for envelope in mapper.map(registered_chunks()):
                    if await request.is_disconnected():
                        return
                    if envelope.event == "token":
                        assistant_parts.append(str(envelope.payload.get("text", "")))
                    yield encode_sse(envelope)
            if assistant_parts:
                await _save_message(container, context, "assistant", "".join(assistant_parts))
        except Exception:
            logger.error(
                "agent_stream_failed",
                extra=audit_fields(
                    trace_id=context.trace_id,
                    thread_id=context.thread_id,
                    user_id=context.user_id,
                    agent_name="procurepilot-main",
                ),
            )
            yield encode_sse(mapper.error())

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _register_interrupts(
    container: ApplicationContainer,
    context: ProcurementContext,
    chunk: Any,
) -> None:
    interrupts = chunk.get("__interrupt__") if isinstance(chunk, dict) else None
    if not interrupts:
        return
    now = datetime.now(UTC)
    for item in interrupts:
        interrupt_id = getattr(item, "id", None)
        value = getattr(item, "value", None)
        if not isinstance(interrupt_id, str) or not isinstance(value, dict):
            continue
        parsed = _interrupt_contract(value)
        if parsed is None:
            continue
        action, resume_kind, summary = parsed
        await container.resumes.register(
            context,
            PendingInterrupt(
                interrupt_id=interrupt_id,
                thread_id=context.thread_id,
                order_action=action,
                resume_kind=resume_kind,
                parameter_summary_hash=hash_parameter_summary(summary),
                created_at=now,
                expires_at=now + timedelta(minutes=15),
            ),
        )


def _interrupt_contract(
    value: dict[str, Any],
) -> tuple[OrderAction, Literal["supplement", "decision"], dict[str, Any]] | None:
    if value.get("kind") == "order_info_request":
        summary = value.get("confirmed_summary")
        if not isinstance(summary, dict):
            return None
        try:
            return OrderAction(str(summary["action"])), "supplement", summary
        except (KeyError, ValueError):
            return None
    requests = value.get("action_requests")
    if not isinstance(requests, list) or not requests or not isinstance(requests[0], dict):
        return None
    name = requests[0].get("name")
    arguments = requests[0].get("args")
    actions = {
        "order_create": OrderAction.CREATE,
        "order_update": OrderAction.UPDATE,
        "order_cancel": OrderAction.CANCEL,
    }
    if name not in actions or not isinstance(arguments, dict):
        return None
    return actions[name], "decision", arguments


@router.post("/stream")
async def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    thread_id = body.thread_id or f"thread-{uuid4()}"
    context = _trusted_context(request, thread_id)
    return _stream(
        request,
        context,
        {"messages": [HumanMessage(content=body.message)]},
        save_user_message=body.message,
    )


@router.post("/{thread_id}/resume")
async def resume_stream(
    thread_id: str,
    body: ResumeRequest,
    request: Request,
) -> StreamingResponse:
    context = _trusted_context(request, thread_id)
    container: ApplicationContainer = request.app.state.container
    resume_model = (
        SupplementResume.model_validate(body.resume.model_dump())
        if body.resume.kind == "supplement"
        else DecisionResume.model_validate(body.resume.model_dump())
    )
    try:
        await container.persistence.threads.require_owner(context)
        resume = await container.resumes.consume_public(
            context,
            body.interrupt_id,
            resume_model,
            now=datetime.now(UTC),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="thread not found") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="interrupt not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="interrupt cannot be resumed") from exc
    return _stream(request, context, Command(resume=resume))
