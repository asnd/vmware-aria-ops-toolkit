"""Chainlit chat UI for EntRAG.

A VMware/Broadcom KB assistant built as an agentic chat: the LLM is given a
local ``kb_search`` tool plus any tools from MCP servers the user connects via
the in-chat MCP button (``@cl.on_mcp_connect``), and decides which to call.

Launch:
    chainlit run src/chat_app.py
    # or, via the console script:
    entrag-serve
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import chainlit as cl

from src.agent import (
    KB_SEARCH_TOOL,
    SYSTEM_PROMPT,
    format_kb_context,
    mcp_tools_to_openai,
    run_agent,
)
from src.config import get_settings
from src.retrieval import RetrievalEngine, create_retrieval_engine

logger = logging.getLogger(__name__)

_MCP_TOOLS_KEY = "mcp_tools"
_ENGINE_KEY = "engine"


def _stringify_mcp_result(result: Any) -> str:
    """Flatten an MCP ``call_tool`` result into plain text for the model."""
    content = getattr(result, "content", None)
    if content is None:
        return str(result)
    parts: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        parts.append(text if text is not None else str(item))
    return "\n".join(parts) if parts else str(result)


@cl.on_chat_start
async def on_chat_start() -> None:
    """Initialise the retrieval engine once per chat session."""
    try:
        engine = create_retrieval_engine()
    except Exception as exc:  # noqa: BLE001 - show config errors in the UI
        logger.exception("Failed to initialise retrieval engine")
        cl.user_session.set(_ENGINE_KEY, None)
        await cl.Message(
            content=f"⚠️ Retrieval engine unavailable: {exc}"
        ).send()
        return
    cl.user_session.set(_ENGINE_KEY, engine)
    cl.user_session.set(_MCP_TOOLS_KEY, {})


@cl.on_mcp_connect
async def on_mcp_connect(connection: Any, session: Any) -> None:
    """Register the tools exposed by a newly connected MCP server."""
    result = await session.list_tools()
    tools = [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        }
        for t in result.tools
    ]
    mcp_tools: dict[str, list[dict]] = cl.user_session.get(_MCP_TOOLS_KEY, {})
    mcp_tools[connection.name] = tools
    cl.user_session.set(_MCP_TOOLS_KEY, mcp_tools)

    names = ", ".join(t["name"] for t in tools) or "(none)"
    await cl.Message(
        content=f"🔌 Connected MCP server **{connection.name}** with tools: {names}"
    ).send()


@cl.on_mcp_disconnect
async def on_mcp_disconnect(name: str, session: Any) -> None:
    """Drop a disconnected MCP server's tools."""
    mcp_tools: dict[str, list[dict]] = cl.user_session.get(_MCP_TOOLS_KEY, {})
    if mcp_tools.pop(name, None) is not None:
        cl.user_session.set(_MCP_TOOLS_KEY, mcp_tools)
    await cl.Message(content=f"🔌 Disconnected MCP server **{name}**").send()


def _make_tool_executor(
    engine: RetrievalEngine,
    tool_to_conn: dict[str, str],
):
    """Build the dispatcher the agent calls to run a tool by name."""

    async def execute_tool(name: str, arguments: dict[str, Any]) -> str:
        if name == "kb_search":
            query = str(arguments.get("query", "")).strip()
            top_k = arguments.get("top_k")
            chunks = await asyncio.to_thread(engine.search, query, top_k)
            return format_kb_context(chunks) or "No KB articles matched that query."

        conn_name = tool_to_conn.get(name)
        if conn_name is None:
            return f"Unknown tool: {name}"

        mcp_session = cl.context.session.mcp_sessions.get(conn_name)
        if mcp_session is None:
            return f"MCP connection '{conn_name}' is no longer active."
        client, _ = mcp_session  # McpSession unpacks to (ClientSession, _)
        result = await client.call_tool(name, arguments)
        return _stringify_mcp_result(result)

    return execute_tool


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Run the agentic tool loop and stream the answer."""
    engine: RetrievalEngine | None = cl.user_session.get(_ENGINE_KEY)
    if engine is None:
        await cl.Message(
            content=(
                "No KB index is available. Run "
                "`entrag-ingest --source ./data/raw --reset` and start a new chat."
            )
        ).send()
        return

    settings = get_settings()
    mcp_tools: dict[str, list[dict]] = cl.user_session.get(_MCP_TOOLS_KEY, {})
    mcp_schemas, tool_to_conn = mcp_tools_to_openai(mcp_tools)
    tools = [KB_SEARCH_TOOL, *mcp_schemas]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *cl.chat_context.to_openai()]
    execute_tool = _make_tool_executor(engine, tool_to_conn)

    answer = cl.Message(content="")
    await answer.send()
    try:
        await run_agent(
            messages=messages,
            tools=tools,
            execute_tool=execute_tool,
            emit=answer.stream_token,
            settings=settings,
        )
    except ValueError as exc:
        answer.content = f"Configuration error: {exc}"
    except Exception as exc:  # noqa: BLE001 - defensive UI boundary
        logger.exception("Agent run failed")
        answer.content = (
            "The KB assistant hit an unexpected error processing that query. "
            "Check the application logs."
        )
        del exc
    await answer.update()


def main() -> None:
    """Console-script entrypoint: launch the Chainlit server."""
    import os

    from chainlit.cli import run_chainlit

    settings = get_settings()
    os.environ.setdefault("CHAINLIT_HOST", settings.server_host)
    os.environ.setdefault("CHAINLIT_PORT", str(settings.server_port))
    run_chainlit(__file__)


if __name__ == "__main__":
    main()
