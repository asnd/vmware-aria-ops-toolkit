"""Tests for the agentic tool-calling loop (src/agent.py)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.agent import (
    _KB_CHUNK_TRUNCATE,
    KB_SEARCH_TOOL,
    format_kb_context,
    mcp_tools_to_openai,
    run_agent,
)
from src.config import Settings
from src.retrieval import RetrievedChunk


def _chunk(article: str = "318867", text: str = "Reboot the host.") -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        score=0.9,
        article_number=article,
        title="Host fails to boot",
        url="https://kb/318867",
        product="ESXi",
        section_type="resolution",
        section_heading="Resolution",
        metadata={},
    )


# ── helpers ──────────────────────────────────────────────────────────────


def test_format_kb_context_includes_citation_and_section():
    out = format_kb_context([_chunk()])
    assert "KB318867" in out
    assert "Resolution" in out
    assert "Reboot the host." in out


def test_format_kb_context_truncates_long_chunks():
    truncated_text = "x" * _KB_CHUNK_TRUNCATE
    text = f"{truncated_text}{'x' * 100}"
    out = format_kb_context([_chunk(text=text)])
    assert text not in out
    assert truncated_text in out
    assert out.endswith(f"{truncated_text}...")
    assert ("x" * (_KB_CHUNK_TRUNCATE + 1)) not in out


def test_format_kb_context_empty():
    assert format_kb_context([]) == ""


def test_mcp_tools_to_openai_flattens_and_maps():
    mcp_tools = {
        "ops": [
            {
                "name": "restart_vm",
                "description": "Restart a VM",
                "input_schema": {"type": "object"},
            },
        ],
        "metrics": [
            {"name": "get_cpu", "description": "CPU usage", "input_schema": {"type": "object"}},
        ],
    }
    schemas, tool_to_conn = mcp_tools_to_openai(mcp_tools)

    assert {s["function"]["name"] for s in schemas} == {"restart_vm", "get_cpu"}
    assert tool_to_conn == {"restart_vm": "ops", "get_cpu": "metrics"}
    assert all(s["type"] == "function" for s in schemas)


def test_mcp_tools_to_openai_collision_first_wins():
    mcp_tools = {
        "a": [{"name": "dup", "description": "from a", "input_schema": {}}],
        "b": [{"name": "dup", "description": "from b", "input_schema": {}}],
    }
    schemas, tool_to_conn = mcp_tools_to_openai(mcp_tools)
    assert len(schemas) == 1
    assert tool_to_conn == {"dup": "a"}


def test_mcp_tools_to_openai_empty():
    schemas, tool_to_conn = mcp_tools_to_openai({})
    assert schemas == []
    assert tool_to_conn == {}


# ── run_agent ────────────────────────────────────────────────────────────


def _settings() -> Settings:
    return Settings(litellm_api_key="sk-test", litellm_model="openai/test")


def _tool_call(call_id: str, name: str, arguments: str):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _message(content: str | None = None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))]
    )


async def _fail_executor(name, args):  # pragma: no cover - should not be called
    raise AssertionError(f"execute_tool unexpectedly called for {name}")


async def _collect(coro_factory):
    tokens: list[str] = []

    async def emit(token: str) -> None:
        tokens.append(token)

    answer = await coro_factory(emit)
    return answer, "".join(tokens)


@pytest.mark.asyncio
async def test_run_agent_direct_answer(monkeypatch):
    """No tool calls: model answers directly, answer is emitted progressively."""
    calls: list[dict] = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return _message(content="Hello world", tool_calls=None)

    monkeypatch.setattr("src.agent.litellm.completion", fake_completion)

    async def run(emit):
        return await run_agent(
            messages=[{"role": "user", "content": "hi"}],
            tools=[KB_SEARCH_TOOL],
            execute_tool=_fail_executor,
            emit=emit,
            settings=_settings(),
        )

    answer, streamed = await _collect(run)
    assert answer == "Hello world"
    assert streamed == "Hello world"  # chunked emission reassembles losslessly
    # A direct answer needs exactly one call, made with tools available.
    assert len(calls) == 1
    assert calls[0]["tools"] == [KB_SEARCH_TOOL]


@pytest.mark.asyncio
async def test_run_agent_executes_tool_then_answers(monkeypatch):
    """Model requests kb_search, result is fed back, then it answers."""
    responses = [
        _message(tool_calls=[_tool_call("c1", "kb_search", '{"query": "boot"}')]),
        _message(content="Cited KB318867", tool_calls=None),
    ]

    def fake_completion(**kwargs):
        return responses.pop(0)

    monkeypatch.setattr("src.agent.litellm.completion", fake_completion)

    executed: list[tuple[str, dict]] = []

    async def execute_tool(name, args):
        executed.append((name, args))
        return "KB318867: reboot"

    async def run(emit):
        return await run_agent(
            messages=[{"role": "user", "content": "boot fails"}],
            tools=[KB_SEARCH_TOOL],
            execute_tool=execute_tool,
            emit=emit,
            settings=_settings(),
        )

    answer, streamed = await _collect(run)
    assert executed == [("kb_search", {"query": "boot"})]
    assert answer == "Cited KB318867"
    assert streamed == "Cited KB318867"


@pytest.mark.asyncio
async def test_run_agent_tool_error_is_surfaced(monkeypatch):
    """A failing tool reports the error back to the model instead of crashing."""
    work_seen: list[dict] = []
    responses = [
        _message(tool_calls=[_tool_call("c1", "kb_search", "{}")]),
        _message(content="done", tool_calls=None),
    ]

    def fake_completion(**kwargs):
        work_seen.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr("src.agent.litellm.completion", fake_completion)

    async def boom(name, args):
        raise RuntimeError("tool exploded")

    async def run(emit):
        return await run_agent(
            messages=[{"role": "user", "content": "q"}],
            tools=[KB_SEARCH_TOOL],
            execute_tool=boom,
            emit=emit,
            settings=_settings(),
        )

    answer, _ = await _collect(run)
    assert answer == "done"
    # The tool result fed to the second call carries the error text.
    second_call_messages = work_seen[-1]["messages"]
    tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
    assert tool_msgs and "tool exploded" in tool_msgs[0]["content"]


@pytest.mark.asyncio
async def test_run_agent_respects_max_rounds(monkeypatch):
    """If the model keeps calling tools, the loop stops and forces a final answer."""
    tool_rounds = {"n": 0}

    def fake_completion(**kwargs):
        # The forced final call passes no tools.
        if not kwargs.get("tools"):
            return _message(content="forced", tool_calls=None)
        tool_rounds["n"] += 1
        return _message(tool_calls=[_tool_call(f"c{tool_rounds['n']}", "kb_search", "{}")])

    monkeypatch.setattr("src.agent.litellm.completion", fake_completion)

    async def execute_tool(name, args):
        return "more"

    async def run(emit):
        return await run_agent(
            messages=[{"role": "user", "content": "q"}],
            tools=[KB_SEARCH_TOOL],
            execute_tool=execute_tool,
            emit=emit,
            settings=_settings(),
            max_rounds=2,
        )

    answer, streamed = await _collect(run)
    assert answer == "forced"
    assert streamed == "forced"
    assert tool_rounds["n"] == 2  # exactly max_rounds tool rounds before forcing
