"""Tests for the multi-round tool-calling loop.

Tests pure helper functions (tc_path, sanitize_tool_result) and
the run_tool_loop / resume_execution flow with mocked providers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from lighterllm.llm.base import ChatResult, ToolCall, defs_to_tools

# The tool_loop module — import from lightercore (shared)
from lighterllm.llm.tool_loop import (
    _pending_executions,
    resume_execution,
    run_tool_loop,
    sanitize_tool_result,
    tc_path,
)


# ── tc_path ───────────────────────────────────────────────────────────────


class TestTcPath:
    """Tests for tc_path helper."""

    def test_simple_path(self):
        """node_search → node.search with empty flags."""
        tc = ToolCall(id="c1", function={"name": "node_search", "arguments": "{}"})
        path, flags = tc_path(tc)
        assert path == "node.search"
        assert flags == {}

    def test_with_flags(self):
        """Extract flags from JSON arguments."""
        tc = ToolCall(id="c2", function={"name": "email_list", "arguments": '{"folder": "INBOX", "limit": 20}'})
        path, flags = tc_path(tc)
        assert path == "email.list"
        assert flags == {"folder": "INBOX", "limit": 20}

    def test_multi_segment(self):
        """Multi-segment tool name: calendar_event_add → calendar.event.add."""
        tc = ToolCall(id="c3", function={"name": "calendar_event_add", "arguments": '{"title": "Meeting"}'})
        path, flags = tc_path(tc)
        assert path == "calendar.event.add"
        assert flags == {"title": "Meeting"}

    def test_invalid_json_flags(self):
        """Invalid JSON arguments → empty flags (no crash)."""
        tc = ToolCall(id="c4", function={"name": "node_list", "arguments": "not-json"})
        path, flags = tc_path(tc)
        assert path == "node.list"
        assert flags == {}


# ── sanitize_tool_result ──────────────────────────────────────────────────


class TestSanitizeToolResult:
    """Tests for sanitize_tool_result helper."""

    def test_plain_dict(self):
        """Plain dict passes through unchanged."""
        result = {"message": "ok", "count": 5}
        assert sanitize_tool_result(result) == result

    def test_parses_json_string(self):
        """JSON-encoded string values get parsed."""
        result = {"labels": '{"en": "Alice", "fr": "Alice"}'}
        cleaned = sanitize_tool_result(result)
        assert cleaned["labels"] == {"en": "Alice", "fr": "Alice"}

    def test_nested_json(self):
        """Nested JSON strings get parsed recursively."""
        result = {"data": '{"items": [{"name": "A"}, {"name": "B"}]}'}
        cleaned = sanitize_tool_result(result)
        assert cleaned["data"]["items"] == [{"name": "A"}, {"name": "B"}]

    def test_list_of_json_strings(self):
        """List items that are JSON strings get parsed."""
        result = {"items": ['{"id": 1}', '{"id": 2}']}
        cleaned = sanitize_tool_result(result)
        assert cleaned["items"] == [{"id": 1}, {"id": 2}]

    def test_short_string_not_parsed(self):
        """Strings of length <= 1 are not parsed."""
        result = {"key": "a"}
        assert sanitize_tool_result(result) == {"key": "a"}

    def test_non_json_string_not_parsed(self):
        """Non-JSON strings pass through unchanged."""
        result = {"name": "hello world"}
        assert sanitize_tool_result(result) == {"name": "hello world"}


# ── defs_to_tools (exercise the conversion) ───────────────────────────────


class TestDefsToTools:
    """Tests for defs_to_tools conversion."""

    def test_basic_conversion(self):
        """Command definitions convert to OpenAI tool format."""
        defs = [
            {
                "path": ["email", "list"],
                "description": "List emails",
                "flags": [{"name": "folder", "type": "string", "help": "Folder name"}],
            },
            {
                "path": ["todo", "add"],
                "description": "Add todo",
                "params": [{"name": "title", "type": "string", "required": True}],
            },
        ]
        tools = defs_to_tools(defs)
        assert len(tools) == 2
        assert tools[0]["function"]["name"] == "email_list"
        assert tools[1]["function"]["name"] == "todo_add"
        assert "folder" in tools[0]["function"]["parameters"]["properties"]
        assert tools[1]["function"]["parameters"]["required"] == ["title"]


# ── run_tool_loop (mocked provider) ───────────────────────────────────────


class FakeDispatcher:
    """Simulates command dispatch for testing."""

    def __init__(self):
        self.calls = []

    def dispatch(self, path: str, flags: dict) -> dict:
        self.calls.append((path, flags))
        return {"type": "status", "data": {"result": f"executed {path}"}}


class TestRunToolLoop:
    """Tests for run_tool_loop core function."""

    def _make_mock_provider(self, responses: list[ChatResult]) -> MagicMock:
        """Create a mock provider that returns given ChatResults in sequence."""
        mock = MagicMock()
        mock.chat_with_tools = AsyncMock()
        mock.chat_with_tools.side_effect = responses
        return mock

    def _make_meta_fn(self, known: set[str] | None = None):
        """Create a get_handler_metadata_fn that returns a stub for known paths."""
        known = known or set()

        def meta_fn(path: str) -> dict | None:
            if path in known:
                return {"description": f"Handler for {path}"}
            return None
        return meta_fn

    def _make_level_fn(self, levels: dict[str, int] | None = None):
        """Create a get_command_level_fn based on a levels dict."""
        levels = levels or {}

        def level_fn(path: str) -> int | None:
            return levels.get(path, None)
        return level_fn

    async def test_text_response_returns_immediately(self):
        """If LLM returns text (no tool calls), return it immediately."""
        mock = self._make_mock_provider([
            ChatResult(content="Hello! How can I help you?"),
        ])
        dispatcher = FakeDispatcher()

        result = await run_tool_loop(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            name="test",
            provider=mock,
            dispatch_fn=dispatcher.dispatch,
            get_handler_metadata_fn=self._make_meta_fn(),
            get_command_level_fn=self._make_level_fn(),
        )

        assert result == "Hello! How can I help you?"
        assert dispatcher.calls == []  # no tools were called

    async def test_read_tool_executes_immediately(self):
        """READ-level tools execute without confirmation."""
        mock = self._make_mock_provider([
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(id="c1", function={"name": "email_list", "arguments": '{"folder": "INBOX"}'}),
                ],
            ),
            # After tool result, LLM returns text
            ChatResult(content="Found 5 emails."),
        ])
        dispatcher = FakeDispatcher()

        result = await run_tool_loop(
            messages=[{"role": "user", "content": "show emails"}],
            tools=defs_to_tools([
                {"path": ["email", "list"], "description": "List emails"},
            ]),
            name="test",
            provider=mock,
            dispatch_fn=dispatcher.dispatch,
            get_handler_metadata_fn=self._make_meta_fn({"email.list"}),
            get_command_level_fn=self._make_level_fn({"email.list": 1}),  # READ=1
        )

        assert result == "Found 5 emails."
        assert dispatcher.calls == [("email.list", {"folder": "INBOX"})]

    async def test_write_tool_returns_confirm_tool(self):
        """WRITE-level tools return confirm_tool response."""
        mock = self._make_mock_provider([
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(id="c1", function={"name": "email_send", "arguments": '{"to": "a@b.com"}'}),
                ],
            ),
        ])
        dispatcher = FakeDispatcher()

        result = await run_tool_loop(
            messages=[{"role": "user", "content": "send email"}],
            tools=defs_to_tools([
                {"path": ["email", "send"], "description": "Send email"},
            ]),
            name="test",
            provider=mock,
            dispatch_fn=dispatcher.dispatch,
            get_handler_metadata_fn=self._make_meta_fn({"email.send"}),
            get_command_level_fn=self._make_level_fn({"email.send": 2}),  # WRITE=2
        )

        assert isinstance(result, dict)
        assert result["type"] == "confirm_tool"
        assert "session_id" in result
        assert len(result["batch"]) == 1
        assert result["batch"][0]["tokens"] == ["email", "send"]
        assert dispatcher.calls == []  # tool NOT executed (pending confirm)

    async def test_mixed_read_write(self):
        """READ executes, WRITE gates, in the same batch."""
        mock = self._make_mock_provider([
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(id="c1", function={"name": "email_list", "arguments": "{}"}),
                    ToolCall(id="c2", function={"name": "todo_add", "arguments": '{"title": "Task"}'}),
                ],
            ),
        ])
        dispatcher = FakeDispatcher()

        result = await run_tool_loop(
            messages=[{"role": "user", "content": "show emails and add task"}],
            tools=defs_to_tools([
                {"path": ["email", "list"], "description": "List"},
                {"path": ["todo", "add"], "description": "Add todo"},
            ]),
            name="test",
            provider=mock,
            dispatch_fn=dispatcher.dispatch,
            get_handler_metadata_fn=self._make_meta_fn({"email.list", "todo.add"}),
            get_command_level_fn=self._make_level_fn({
                "email.list": 1,   # READ
                "todo.add": 2,     # WRITE
            }),
        )

        assert isinstance(result, dict)
        assert result["type"] == "confirm_tool"
        # READ tool was executed
        assert dispatcher.calls == [("email.list", {})]
        # Only the WRITE tool is in the confirm batch
        assert len(result["batch"]) == 1
        assert result["batch"][0]["tokens"] == ["todo", "add"]

    async def test_max_rounds_exhausted(self):
        """Returns None when loop exhausts without producing text."""
        mock = self._make_mock_provider([
            ChatResult(
                content=None,
                tool_calls=[ToolCall(id="c1", function={"name": "email_list", "arguments": "{}"})],
            )
            for _ in range(3)  # exceed max_rounds=2
        ])
        dispatcher = FakeDispatcher()

        result = await run_tool_loop(
            messages=[{"role": "user", "content": "loop"}],
            tools=defs_to_tools([{"path": ["email", "list"], "description": "List"}]),
            name="test",
            provider=mock,
            dispatch_fn=dispatcher.dispatch,
            get_handler_metadata_fn=self._make_meta_fn({"email.list"}),
            get_command_level_fn=self._make_level_fn({"email.list": 1}),
            max_rounds=2,
        )

        assert result is None


# ── resume_execution ─────────────────────────────────────────────────────


class TestResumeExecution:
    """Tests for resume_execution after confirm_tool."""

    async def test_approve_write_tool(self):
        """Approved write tool executes and loop continues."""
        mock = MagicMock()
        mock.chat_with_tools = AsyncMock(side_effect=[
            ChatResult(content="Done! Task created."),
        ])
        dispatcher = FakeDispatcher()

        # Manually seed _pending_executions
        session_id = "test-session"
        _pending_executions[session_id] = {
            "messages": [
                {"role": "system", "content": "You are a helper."},
                {"role": "user", "content": "add a task"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "todo_add", "arguments": '{"title": "Buy milk"}'}},
                ]},
            ],
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "todo_add", "arguments": '{"title": "Buy milk"}'}},
            ],
            "tools": [{"type": "function", "function": {"name": "todo_add", "description": "Add todo"}}],
            "name": "test",
            "write_paths": {("todo", "add"): {"tokens": ["todo", "add"], "flags": {"title": "Buy milk"}}},
        }

        def meta_fn(path):
            return {"description": "Add todo"} if path == "todo.add" else None

        def level_fn(path):
            return 2 if path == "todo.add" else None  # WRITE

        result = await resume_execution(
            session_id=session_id,
            decisions={0: True},
            provider=mock,
            dispatch_fn=dispatcher.dispatch,
            get_handler_metadata_fn=meta_fn,
            get_command_level_fn=level_fn,
        )

        assert result == "Done! Task created."
        # The write tool was executed
        assert len(dispatcher.calls) >= 1
        assert dispatcher.calls[0][0] == "todo.add"

    async def test_reject_write_tool(self):
        """Rejected write tool records user rejection."""
        mock = MagicMock()
        mock.chat_with_tools = AsyncMock(side_effect=[
            ChatResult(content="Skipped."),
        ])
        dispatcher = FakeDispatcher()

        session_id = "test-reject"
        _pending_executions[session_id] = {
            "messages": [
                {"role": "system", "content": "You are a helper."},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "todo_add", "arguments": '{"title": "Bad task"}'}},
                ]},
            ],
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "todo_add", "arguments": '{"title": "Bad task"}'}},
            ],
            "tools": [],
            "name": "test",
            "write_paths": {("todo", "add"): {"tokens": ["todo", "add"], "flags": {"title": "Bad task"}}},
        }

        def meta_fn(path):
            return {"description": "Add todo"} if path == "todo.add" else None

        def level_fn(path):
            return 2 if path == "todo.add" else None

        result = await resume_execution(
            session_id=session_id,
            decisions={0: False},
            provider=mock,
            dispatch_fn=dispatcher.dispatch,
            get_handler_metadata_fn=meta_fn,
            get_command_level_fn=level_fn,
        )

        assert result == "Skipped."
        # Tool was NOT dispatched (rejected)
        assert dispatcher.calls == []

    def test_invalid_session_raises(self):
        """Unknown session_id raises LookupError."""
        import pytest as _pytest

        with _pytest.raises(LookupError, match="not found or expired"):
            # Must be called in async context for the raise to work
            import asyncio
            asyncio.run(resume_execution(
                session_id="nonexistent",
                provider=MagicMock(),
                dispatch_fn=lambda p, f: {},
                get_handler_metadata_fn=lambda p: None,
                get_command_level_fn=lambda p: None,
            ))


# ── Cleanup ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_pending():
    """Clear _pending_executions before each test."""
    _pending_executions.clear()
    yield
