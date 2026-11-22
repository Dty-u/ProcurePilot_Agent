"""ProcurePilot FastAPI 工厂；模块导入不连接外部系统。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api_view.auth import HeaderAuthenticator
from api_view.container import open_application_container
from api_view.routes.chat import router as chat_router
from api_view.routes.history import router as history_router
from procurepilot.config import Settings

ContainerFactory = Callable[[Settings], Any]


def create_app(
    settings: Settings | None = None,
    *,
    container_factory: ContainerFactory = open_application_container,
) -> FastAPI:
    configured = settings or Settings()
    authenticator = HeaderAuthenticator(configured)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with container_factory(configured) as container:
            app.state.container = container
            yield

    app = FastAPI(title="ProcurePilot API", version="1.0", lifespan=lifespan)
    app.state.authenticator = authenticator
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured.api_cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-User-ID", "X-User-Name", "X-Roles"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        # 默认 FastAPI 响应会回显原始 input，这里只保留字段位置和类型。
        details = [
            {"loc": item.get("loc", ()), "type": item.get("type", "validation_error")}
            for item in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": details})

    app.include_router(chat_router)
    app.include_router(history_router)
    return app
