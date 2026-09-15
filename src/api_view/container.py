"""FastAPI 组合根：显式管理 MySQL、MCP、Sandbox 和 Agent 生命周期。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import cast

from langchain_core.language_models import BaseChatModel
from mcp import Client

from agent.application import create_agent_application
from agent.context import ProcurementContext
from agent.main_agent import MainAgent
from agent.model_factory import create_chat_model
from agent.persistence import AgentPersistence, open_agent_persistence
from agent.resume_service import ResumeService, open_resume_service
from agent.sandbox.deepagents_backend import DeepAgentsSandboxBackend
from agent.sandbox.opensandbox_backend import OpenSandboxAdapter, OpenSandboxConfig
from agent.sandbox.skills import sync_approved_skills
from agent.tools.procurement_read import MCPClientProtocol
from api_view.message_repository import MessageRepository, open_message_repository
from mcp_server.bootstrap import create_service_container
from mcp_server.context import CallerContextProvider, ToolCallerContext
from mcp_server.server_main import create_mcp_server
from procurepilot.config import Settings


class _RequestContextProvider(CallerContextProvider):
    def __init__(self, context: ProcurementContext) -> None:
        self._context = ToolCallerContext(
            user_id=context.user_id,
            roles=context.roles,
            trace_id=context.trace_id,
            thread_id=context.thread_id,
        )

    async def get_context(self) -> ToolCallerContext:
        return self._context


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    model: BaseChatModel
    persistence: AgentPersistence
    resumes: ResumeService
    messages: MessageRepository

    @asynccontextmanager
    async def open_agent(self, context: ProcurementContext) -> AsyncIterator[MainAgent]:
        image = self.settings.opensandbox_image
        if image is None:
            raise RuntimeError("OPENSANDBOX_IMAGE with sha256 digest is required")
        service_container = create_service_container(
            self.settings, _RequestContextProvider(context)
        )
        server = create_mcp_server(self.settings, service_container)
        sandbox = OpenSandboxAdapter(
            OpenSandboxConfig(
                base_url=str(self.settings.opensandbox_base_url),
                api_key=(
                    self.settings.opensandbox_api_key.get_secret_value()
                    if self.settings.opensandbox_api_key is not None
                    else None
                ),
                image=image,
                cpu=self.settings.opensandbox_cpu,
                memory=self.settings.opensandbox_memory,
                disk=self.settings.opensandbox_disk,
                max_file_bytes=self.settings.opensandbox_max_file_bytes,
                max_processes=self.settings.opensandbox_max_processes,
                ttl=timedelta(seconds=self.settings.opensandbox_ttl_seconds),
                ready_timeout=timedelta(
                    seconds=self.settings.opensandbox_ready_timeout_seconds
                ),
            )
        )
        await sandbox.create()
        try:
            skill_paths = await sync_approved_skills(sandbox)
            backend = DeepAgentsSandboxBackend(sandbox)
            async with Client(
                server,
                read_timeout_seconds=self.settings.request_timeout_seconds,
            ) as client:
                agent = await create_agent_application(
                    self.model,
                    cast(MCPClientProtocol, client),
                    context,
                    checkpointer=self.persistence.checkpointer,
                    store=self.persistence.store,
                    backend=backend,
                    skills=skill_paths,
                )
                yield agent
        finally:
            await sandbox.close()


@asynccontextmanager
async def open_application_container(
    settings: Settings,
) -> AsyncIterator[ApplicationContainer]:
    """按声明顺序打开资源，任一失败由 AsyncExitStack 逆序关闭。"""

    model = create_chat_model(settings)
    async with AsyncExitStack() as stack:
        persistence = await stack.enter_async_context(open_agent_persistence(settings))
        resumes = await stack.enter_async_context(open_resume_service(settings))
        messages = await stack.enter_async_context(open_message_repository(settings))
        yield ApplicationContainer(settings, model, persistence, resumes, messages)
