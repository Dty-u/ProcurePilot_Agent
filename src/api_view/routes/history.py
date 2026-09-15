"""按可信用户隔离的展示历史路由。"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from api_view.container import ApplicationContainer
from api_view.routes.chat import _trusted_context

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
async def list_threads(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    context = _trusted_context(request, "history-list")
    container: ApplicationContainer = request.app.state.container
    threads = await container.messages.list_threads(context, offset=offset, limit=limit)
    return {"items": threads, "offset": offset, "limit": limit}


@router.get("/{thread_id}")
async def get_thread(thread_id: str, request: Request) -> dict[str, Any]:
    context = _trusted_context(request, thread_id)
    container: ApplicationContainer = request.app.state.container
    try:
        await container.persistence.threads.require_owner(context)
    except (PermissionError, LookupError) as exc:
        raise HTTPException(status_code=404, detail="thread not found") from exc
    return {"items": await container.messages.list_messages(context)}


@router.delete("/{thread_id}")
async def delete_thread(thread_id: str, request: Request) -> dict[str, int]:
    context = _trusted_context(request, thread_id)
    container: ApplicationContainer = request.app.state.container
    try:
        await container.persistence.threads.require_owner(context)
    except (PermissionError, LookupError) as exc:
        raise HTTPException(status_code=404, detail="thread not found") from exc
    return {"deleted_messages": await container.messages.delete_thread(context)}
