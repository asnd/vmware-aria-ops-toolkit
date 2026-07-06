"""Entry point for the EntRAG MCP server.

Supports two transport modes:
- stdio: For local MCP clients (Claude Desktop, etc.)
- http: Streamable HTTP with optional OAuth2/Keycloak bearer token auth

Usage:
    entrag-mcp                         # stdio (default)
    ENTRAG_MCP_TRANSPORT=http entrag-mcp  # HTTP on port 8080
"""

from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import Server
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.routes import build_resource_metadata_url, create_protected_resource_routes
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.config import Settings, get_settings
from src.mcp_server.http_auth import JWTTokenVerifier
from src.mcp_server.server import create_server

logger = logging.getLogger(__name__)


async def _health_check(_request: Request) -> JSONResponse:
    """Health endpoint for container orchestration."""
    settings = get_settings()
    from pathlib import Path

    lancedb_path = Path(settings.lancedb_path)
    index_ready = lancedb_path.exists()
    status = "ok" if index_ready else "degraded"
    return JSONResponse(
        {"status": status, "index_available": index_ready},
        status_code=200 if index_ready else 503,
    )


def create_http_app(
    *,
    server: Server[Any, Any] | None = None,
    settings: Settings | None = None,
    session_manager: StreamableHTTPSessionManager | None = None,
) -> Starlette:
    """Build the Starlette ASGI app with optional OAuth2 middleware."""
    s = settings or get_settings()
    server = server or create_server()

    if session_manager is None:
        session_manager = StreamableHTTPSessionManager(
            app=server,
            event_store=None,
            json_response=False,
            stateless=True,
        )

    streamable_http_app = StreamableHTTPASGIApp(session_manager)
    routes: list[Route] = [Route("/health", endpoint=_health_check, methods=["GET"])]
    middleware: list[Middleware] = []
    mcp_endpoint: Any = streamable_http_app

    if s.mcp_oauth_enabled:
        issuer_url = s.mcp_oauth_issuer_url
        resource_server_url = s.mcp_oauth_resource_server_url
        if issuer_url is None or resource_server_url is None:
            raise RuntimeError(
                "OAuth is enabled but issuer/resource-server URLs are missing — "
                "this should have been caught by Settings validation."
            )
        verifier = JWTTokenVerifier(s)
        middleware = [
            Middleware(AuthenticationMiddleware, backend=BearerAuthBackend(verifier)),
            Middleware(AuthContextMiddleware),
        ]
        resource_metadata_url = build_resource_metadata_url(resource_server_url)
        routes.extend(
            create_protected_resource_routes(
                resource_url=resource_server_url,
                authorization_servers=[issuer_url],
                scopes_supported=s.mcp_oauth_required_scopes,
            )
        )
        mcp_endpoint = RequireAuthMiddleware(
            streamable_http_app,
            s.mcp_oauth_required_scopes,
            resource_metadata_url,
        )
        logger.info(
            "MCP OAuth2 enabled — issuer=%s, resource=%s, scopes=%s",
            issuer_url,
            resource_server_url,
            s.mcp_oauth_required_scopes,
        )

    routes.append(Route("/mcp", endpoint=mcp_endpoint))

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with session_manager.run():
            yield

    return Starlette(routes=routes, middleware=middleware, lifespan=lifespan)


def _configure_logging(level: str) -> None:
    """Set up structured logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main() -> None:
    """Entry point: run the MCP server in stdio or HTTP mode."""
    s = get_settings()
    _configure_logging(s.mcp_log_level)

    server = create_server()

    if s.mcp_transport == "http":
        import uvicorn

        async def run_http() -> None:
            loop = asyncio.get_event_loop()
            app = create_http_app(server=server, settings=s)
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=s.mcp_port,
                log_level=s.mcp_log_level.lower(),
            )
            uvicorn_server = uvicorn.Server(config)

            def request_shutdown(received_signal: signal.Signals) -> None:
                logger.info("Shutting down EntRAG MCP server after %s...", received_signal.name)
                uvicorn_server.should_exit = True

            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(
                    sig,
                    request_shutdown,
                    sig,
                )

            logger.info("Starting EntRAG MCP HTTP server on 0.0.0.0:%d", s.mcp_port)
            await uvicorn_server.serve()

        asyncio.run(run_http())
    else:
        from mcp.server.stdio import stdio_server

        async def run_stdio() -> None:
            async with stdio_server() as (read_stream, write_stream):
                logger.info("Starting EntRAG MCP server (stdio transport)")
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )

        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
