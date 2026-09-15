"""Executable entry point for the standalone ProcurePilot MCP process."""

from mcp_server.bootstrap import create_service_container
from mcp_server.context import MissingCallerContextProvider
from mcp_server.server_main import create_mcp_server
from procurepilot.config import Settings


def main() -> None:
    settings = Settings()
    container = create_service_container(
        settings,
        MissingCallerContextProvider(),
    )
    server = create_mcp_server(settings, container)
    if settings.mcp_transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(
            transport=settings.mcp_transport,
            host=settings.mcp_host,
            port=settings.mcp_port,
        )


if __name__ == "__main__":
    main()
