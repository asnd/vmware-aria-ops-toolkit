"""Agentic tool-calling loop for the EntRAG chat.

The LLM is given a local ``kb_search`` tool plus any tools exposed by MCP
servers the user connects at runtime, and decides which to call each turn.
Tool-resolution rounds run non-streamed; the final user-facing answer is
streamed token by token via the ``emit`` callback.

The orchestration here is deliberately Chainlit-free so it can be unit tested
with fakes — the only injected dependencies are ``execute_tool`` and ``emit``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import litellm

from src.config import Settings

if TYPE_CHECKING:
    from src.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)

# Reasoning models (e.g. nemotron-3-super) spend tokens on internal thinking
# before emitting content, so the budget must comfortably exceed the answer.
MAX_TOKENS = 4096
TEMPERATURE = 0.1
DEFAULT_MAX_ROUNDS = 4
# Hard timeout per LiteLLM call — reasoning models can legitimately take 30-60s,
# but we don't want to hang indefinitely if the corporate proxy drops the connection.
REQUEST_TIMEOUT = 120
# Max characters of KB text injected per chunk as a tool result.
# Keeps total context manageable for the reasoning model.
_KB_CHUNK_TRUNCATE = 1200
# Characters per emitted chunk when rendering the final answer progressively.
_EMIT_CHUNK_SIZE = 24

SYSTEM_PROMPT = """\
You are an expert VMware/Broadcom support engineer with deep knowledge of \
vSphere, vCenter, ESXi, NSX, vSAN, and related products.

You have tools available:
- `kb_search`: search the indexed VMware/Broadcom knowledge base. Use it for \
any product, error, symptom, or version question before answering.
- Any additional tools exposed by MCP servers the user has connected.

Rules:
1. For VMware/Broadcom questions, call `kb_search` first and ground your answer \
in the returned excerpts. Cite KB article numbers (e.g. KB318867) for every claim.
2. Prefer Resolution and Workaround sections when present.
3. Use connected MCP tools when they are the right way to fulfil the request.
4. If the tools do not return enough information, say so explicitly rather than \
inventing details.\
"""

KB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "kb_search",
        "description": (
            "Search the indexed VMware/Broadcom knowledge base using hybrid "
            "vector + keyword search. Returns the top matching KB excerpts with "
            "article citations and section types (Symptom, Cause, Resolution)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (error message, product, symptom, version).",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of excerpts to return (default 5).",
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        },
    },
}

# execute_tool(name, arguments) -> result string
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]
# emit(token) -> None — streams a single token of the final answer to the UI
TokenEmitter = Callable[[str], Awaitable[None]]


def format_kb_context(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as a citation-friendly context block."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        section = (
            chunk.section_type.replace("_", " ").title() if chunk.section_type else "General"
        )
        heading = f" — {chunk.section_heading}" if chunk.section_heading else ""
        parts.append(
            f"[{i}] KB{chunk.article_number}: {chunk.title}\n"
            f"Section: {section}{heading}\n\n"
            f"{_truncate_kb_text(chunk.text)}"
        )
    return "\n\n---\n\n".join(parts)


def _truncate_kb_text(text: str) -> str:
    """Limit KB context size while making truncation visible to the model."""
    if len(text) <= _KB_CHUNK_TRUNCATE:
        return text
    return f"{text[:_KB_CHUNK_TRUNCATE]}..."


def mcp_tools_to_openai(
    mcp_tools: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Flatten per-connection MCP tool lists into OpenAI tool schemas.

    Returns the schema list and a ``{tool_name: connection_name}`` dispatch map.
    On a name collision across connections, the first connection wins and the
    duplicate is skipped (logged) so dispatch stays unambiguous.
    """
    schemas: list[dict[str, Any]] = []
    tool_to_conn: dict[str, str] = {}
    for conn_name, tools in mcp_tools.items():
        for tool in tools:
            name = tool.get("name")
            if not name:
                continue
            if name in tool_to_conn:
                logger.warning(
                    "MCP tool name collision: %r from %r already provided by %r; skipping.",
                    name,
                    conn_name,
                    tool_to_conn[name],
                )
                continue
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description") or f"MCP tool {name}",
                        "parameters": tool.get("input_schema")
                        or {"type": "object", "properties": {}},
                    },
                }
            )
            tool_to_conn[name] = conn_name
    return schemas, tool_to_conn


def _complete(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    settings: Settings,
) -> Any:
    """Single non-streamed LiteLLM call. Tools are attached only when provided."""
    kwargs: dict[str, Any] = {
        "model": settings.litellm_model,
        "messages": messages,
        "api_base": settings.litellm_base_url,
        "api_key": settings.litellm_api_key,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "request_timeout": REQUEST_TIMEOUT,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return litellm.completion(**kwargs)


async def _emit_chunked(text: str, emit: TokenEmitter) -> None:
    """Stream a completed answer to the UI in small chunks for progressive render."""
    for i in range(0, len(text), _EMIT_CHUNK_SIZE):
        await emit(text[i : i + _EMIT_CHUNK_SIZE])


def _assistant_tool_call_message(msg: Any) -> dict[str, Any]:
    """Serialise an assistant message that requested tool calls for replay."""
    return {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ],
    }


async def run_agent(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    execute_tool: ToolExecutor,
    emit: TokenEmitter,
    settings: Settings,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> str:
    """Run tool-calling rounds, emitting the final answer via ``emit``.

    Each round is a non-streamed call: if the model requests tools they are
    executed and fed back; the first round that returns no tool calls is the
    final answer, emitted progressively. If the round budget is exhausted, a
    last tool-free call forces a conclusion. Returns the full answer text.

    LiteLLM calls run in a worker thread so the async event loop is not blocked
    during the (synchronous) SDK request.
    """
    work = list(messages)

    for _ in range(max_rounds):
        response = await asyncio.to_thread(_complete, work, tools, settings)
        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            answer = msg.content or ""
            await _emit_chunked(answer, emit)
            return answer

        work.append(_assistant_tool_call_message(msg))
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = await execute_tool(tc.function.name, args)
            except Exception as exc:  # noqa: BLE001 - surface tool errors to the model
                logger.exception("Tool %s failed", tc.function.name)
                result = f"Tool '{tc.function.name}' failed: {exc}"
            work.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": result,
                }
            )

    # Round budget exhausted while still calling tools: force a tool-free answer.
    response = await asyncio.to_thread(_complete, work, None, settings)
    answer = response.choices[0].message.content or ""
    await _emit_chunked(answer, emit)
    return answer
