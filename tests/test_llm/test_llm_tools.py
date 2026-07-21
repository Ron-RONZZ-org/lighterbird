"""Tests for the LLM tool registry and its domain handlers.

Tests cover:
    - The ``@llm_tool()`` decorator / registration
    - ``get_llm_tools()`` OpenAI format conversion
    - ``dispatch_llm_tool()`` dispatch and error handling
    - ``get_llm_tool_level()`` permission resolution
    - Query helpers (``is_llm_tool``, ``get_llm_tool_names``)
    - ``system.now`` handler
    - ``email.find`` handler with mocked service
    - Integration with ``tc_path`` (underscore → dot conversion)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from lighterllm.llm.base import ToolCall
from lighterllm.llm.tool_loop import tc_path
from lightercore.permissions import PermissionLevel

from lighterbird.server.llm.tools import (
    _llm_registry,
    dispatch_llm_tool,
    get_llm_tool_level,
    get_llm_tool_metadata,
    get_llm_tool_names,
    get_llm_tools,
    is_llm_tool,
    llm_tool,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _clear_registry():
    """Clear the LLM tool registry (for test isolation)."""
    _llm_registry.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Decorator & Registration
# ═══════════════════════════════════════════════════════════════════════════════


class TestLlmToolDecorator:
    """Tests for the @llm_tool() decorator."""

    def setup_method(self):
        _clear_registry()

    def test_registers_handler(self):
        """A decorated function is registered in the registry."""
        @llm_tool(
            name="test.hello",
            description="Says hello",
            params=[{"name": "name", "type": "string", "description": "Who to greet"}],
            permission_level=PermissionLevel.READ,
        )
        def hello(name: str = "") -> dict:
            return {"success": True, "data": f"Hello {name}!"}

        assert "test.hello" in _llm_registry
        entry = _llm_registry["test.hello"]
        assert entry["name"] == "test_hello"  # underscore format
        assert entry["description"] == "Says hello"
        assert entry["permission_level"] == PermissionLevel.READ
        assert entry["parameters"]["properties"]["name"]["type"] == "string"

    def test_executes_handler(self):
        """The registered handler can be called via dispatch."""
        @llm_tool(
            name="test.greet",
            description="Greet someone",
            params=[{"name": "name", "type": "string", "description": "Name", "required": True}],
            permission_level=PermissionLevel.WRITE,
        )
        def greet(name: str = "") -> dict:
            return {"success": True, "data": f"Hi {name}!"}

        result = dispatch_llm_tool("test.greet", {"name": "Alice"})
        assert result["success"] is True
        assert result["data"] == "Hi Alice!"

    def test_default_permission_is_read(self):
        """Default permission level is READ."""
        @llm_tool(name="test.default", description="Default perm")
        def default_perm() -> dict:
            return {"success": True}

        assert _llm_registry["test.default"]["permission_level"] == PermissionLevel.READ

    def test_writes_permission_level(self):
        """WRITE and DESTRUCTIVE levels are stored correctly."""
        @llm_tool(name="test.write", description="Write", permission_level=PermissionLevel.WRITE)
        def write_tool() -> dict:
            return {"success": True}

        @llm_tool(name="test.destructive", description="Destructive", permission_level=PermissionLevel.DESTRUCTIVE)
        def destructive_tool() -> dict:
            return {"success": True}

        assert _llm_registry["test.write"]["permission_level"] == PermissionLevel.WRITE
        assert _llm_registry["test.destructive"]["permission_level"] == PermissionLevel.DESTRUCTIVE

    def test_invalid_name_raises(self):
        """Names with invalid characters raise ValueError."""
        with pytest.raises(ValueError, match="Invalid LLM tool name"):

            @llm_tool(name="", description="empty")
            def empty() -> dict:
                return {"success": True}

    def test_params_conversion(self):
        """Parameter types are mapped correctly to JSON Schema types."""
        @llm_tool(
            name="test.types",
            description="Type mapping",
            params=[
                {"name": "s", "type": "string", "description": "A string"},
                {"name": "n", "type": "number", "description": "A number"},
                {"name": "b", "type": "boolean", "description": "A boolean"},
                {"name": "i", "type": "integer", "description": "An integer"},
            ],
        )
        def types_tool(**kwargs) -> dict:
            return {"success": True}

        params = _llm_registry["test.types"]["parameters"]
        assert params["properties"]["s"]["type"] == "string"
        assert params["properties"]["n"]["type"] == "number"
        assert params["properties"]["b"]["type"] == "boolean"
        assert params["properties"]["i"]["type"] == "integer"

    def test_required_params(self):
        """Params with required=True appear in the required list."""
        @llm_tool(
            name="test.req",
            description="Required params",
            params=[
                {"name": "reqd", "type": "string", "description": "Required", "required": True},
                {"name": "opt", "type": "string", "description": "Optional"},
            ],
        )
        def req_tool(**kwargs) -> dict:
            return {"success": True}

        assert _llm_registry["test.req"]["parameters"]["required"] == ["reqd"]

    def teardown_method(self):
        _clear_registry()


# ═══════════════════════════════════════════════════════════════════════════════
# get_llm_tools
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetLlmTools:
    """Tests for get_llm_tools() OpenAI format conversion."""

    def setup_method(self):
        _clear_registry()
        self._register_tools()

    def _register_tools(self):
        @llm_tool(name="alpha.one", description="First tool", params=[
            {"name": "x", "type": "string", "description": "Param X"},
        ])
        def tool1(x: str = "") -> dict:
            return {"success": True}

        @llm_tool(name="beta.two", description="Second tool", permission_level=PermissionLevel.WRITE)
        def tool2() -> dict:
            return {"success": True}

    def test_returns_list(self):
        """get_llm_tools() returns a list of tool dicts."""
        tools = get_llm_tools()
        assert isinstance(tools, list)
        assert len(tools) == 2

    def test_openai_format(self):
        """Each tool has OpenAI function-calling format."""
        tools = get_llm_tools()
        for t in tools:
            assert t["type"] == "function"
            assert "function" in t
            assert "name" in t["function"]
            assert "description" in t["function"]
            assert "parameters" in t["function"]
            assert t["function"]["parameters"]["type"] == "object"

    def test_underscore_names(self):
        """Tool names use underscores for tc_path compatibility."""
        tools = get_llm_tools()
        names = {t["function"]["name"] for t in tools}
        assert "alpha_one" in names
        assert "beta_two" in names
        # Verify tc_path round-trip: alpha_one → alpha.one
        tc = ToolCall(id="t1", function={"name": "alpha_one", "arguments": "{}"})
        path, _ = tc_path(tc)
        assert path == "alpha.one"

    def test_permission_not_in_openai_output(self):
        """Permission level is NOT part of the OpenAI tool definition."""
        tools = get_llm_tools()
        for t in tools:
            assert "permission_level" not in t["function"]
            assert "permission" not in t["function"]

    def test_empty_registry(self):
        """Empty registry returns empty list."""
        _clear_registry()
        assert get_llm_tools() == []

    def teardown_method(self):
        _clear_registry()


# ═══════════════════════════════════════════════════════════════════════════════
# dispatch_llm_tool
# ═══════════════════════════════════════════════════════════════════════════════


class TestDispatchLlmTool:
    """Tests for dispatch_llm_tool()."""

    def setup_method(self):
        _clear_registry()
        self._register_tools()

    def _register_tools(self):
        @llm_tool(name="tool.echo", description="Echo")
        def echo(msg: str = "") -> dict:
            return {"success": True, "data": msg}

        @llm_tool(name="tool.fail", description="Fails")
        def fail() -> dict:
            raise RuntimeError("Intentional failure")

        @llm_tool(name="tool.complex", description="Complex", params=[
            {"name": "a", "type": "string", "description": "A"},
            {"name": "b", "type": "number", "description": "B"},
        ])
        def complex_tool(a: str = "", b: int = 0) -> dict:
            return {"success": True, "data": {"a": a, "b": b}}

    def test_known_tool(self):
        """Known tool dispatches correctly."""
        result = dispatch_llm_tool("tool.echo", {"msg": "hello"})
        assert result["success"] is True
        assert result["data"] == "hello"

    def test_unknown_tool(self):
        """Unknown tool returns error."""
        result = dispatch_llm_tool("nope", {})
        assert result["success"] is False
        assert "Unknown LLM tool" in result["error"]

    def test_handler_exception(self):
        """Handler exception is caught and returned as error."""
        result = dispatch_llm_tool("tool.fail", {})
        assert result["success"] is False
        assert "Intentional failure" in result["error"]

    def test_multiple_params(self):
        """Multiple named params pass through correctly."""
        result = dispatch_llm_tool("tool.complex", {"a": "hello", "b": 42})
        assert result["success"] is True
        assert result["data"]["a"] == "hello"
        assert result["data"]["b"] == 42

    def teardown_method(self):
        _clear_registry()


# ═══════════════════════════════════════════════════════════════════════════════
# get_llm_tool_level
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetLlmToolLevel:
    """Tests for get_llm_tool_level() permission callback."""

    def setup_method(self):
        _clear_registry()

    def test_known_tool_returns_level(self):
        """Known tool returns its permission level."""
        @llm_tool(name="perm.read", description="Read", permission_level=PermissionLevel.READ)
        def r() -> dict:
            return {"success": True}

        @llm_tool(name="perm.write", description="Write", permission_level=PermissionLevel.WRITE)
        def w() -> dict:
            return {"success": True}

        @llm_tool(name="perm.destructive", description="Destructive", permission_level=PermissionLevel.DESTRUCTIVE)
        def d() -> dict:
            return {"success": True}

        assert get_llm_tool_level("perm.read") == PermissionLevel.READ
        assert get_llm_tool_level("perm.write") == PermissionLevel.WRITE
        assert get_llm_tool_level("perm.destructive") == PermissionLevel.DESTRUCTIVE

    def test_unknown_tool_returns_none(self):
        """Unknown tool returns None (tool loop treats as READ)."""
        assert get_llm_tool_level("unknown.tool") is None

    def test_can_pass_to_run_tool_loop(self):
        """get_llm_tool_level has the right signature for run_tool_loop's get_tool_level_fn."""
        import inspect
        sig = inspect.signature(get_llm_tool_level)
        assert "path" in sig.parameters
        # It should accept a single string arg and return PermissionLevel | None
        result = get_llm_tool_level("anything.here")
        assert result is None or isinstance(result, PermissionLevel)

    def teardown_method(self):
        _clear_registry()


# ═══════════════════════════════════════════════════════════════════════════════
# Query helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestQueryHelpers:
    """Tests for is_llm_tool() and get_llm_tool_names()."""

    def setup_method(self):
        _clear_registry()
        @llm_tool(name="alpha.first", description="First")
        def a1() -> dict:
            return {"success": True}

        @llm_tool(name="alpha.second", description="Second")
        def a2() -> dict:
            return {"success": True}

        @llm_tool(name="beta.only", description="Only")
        def b1() -> dict:
            return {"success": True}

    def test_is_llm_tool(self):
        """is_llm_tool checks correctly."""
        assert is_llm_tool("alpha.first") is True
        assert is_llm_tool("alpha.second") is True
        assert is_llm_tool("beta.only") is True
        assert is_llm_tool("nonexistent") is False
        assert is_llm_tool("") is False

    def test_get_llm_tool_names_sorted(self):
        """Names returned sorted alphabetically."""
        names = get_llm_tool_names()
        assert names == ["alpha.first", "alpha.second", "beta.only"]
        assert names == sorted(names)

    def teardown_method(self):
        _clear_registry()


# ═══════════════════════════════════════════════════════════════════════════════
# system.now
# ═══════════════════════════════════════════════════════════════════════════════


class TestSystemNow:
    """Tests for the system.now tool."""

    def _now(self) -> dict:
        from lighterbird.server.llm.tools.system import llm_system_now
        return llm_system_now()

    def test_returns_success(self):
        """system.now returns success with timestamp data."""
        result = self._now()
        assert result["success"] is True
        assert "data" in result
        assert "utc" in result["data"]
        assert "local" in result["data"]
        assert "timezone" in result["data"]
        assert "iso" in result["data"]

    def test_utc_format(self):
        """UTC field ends with Z."""
        result = self._now()
        assert result["data"]["utc"].endswith("Z")

    def test_registered(self):
        """system.now is registered in the tool registry."""
        assert is_llm_tool("system.now")
        assert get_llm_tool_level("system.now") == PermissionLevel.READ

    def test_dispatch_works(self):
        """system.now works via dispatch too."""
        result = dispatch_llm_tool("system.now", {})
        assert result["success"] is True
        assert "utc" in result["data"]


# ═══════════════════════════════════════════════════════════════════════════════
# tc_path integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestTcPathIntegration:
    """Tests that LLM tool naming conventions work with tc_path()."""

    def test_single_segment(self):
        """system.now → system.now"""
        tc = ToolCall(id="t1", function={"name": "system_now", "arguments": "{}"})
        path, _ = tc_path(tc)
        assert path == "system.now"

    def test_two_segments(self):
        """email.find → email.find"""
        tc = ToolCall(id="t2", function={"name": "email_find", "arguments": '{"query": "hello"}'})
        path, flags = tc_path(tc)
        assert path == "email.find"
        assert flags == {"query": "hello"}

    def test_three_segments(self):
        """email.accounts.find → email.accounts.find"""
        tc = ToolCall(id="t3", function={"name": "email_accounts_find", "arguments": "{}"})
        path, _ = tc_path(tc)
        assert path == "email.accounts.find"

    def test_kebab_case(self):
        """User-defined commands with hyphens: user_commands_run → user.commands.run"""
        tc = ToolCall(id="t4", function={"name": "user_commands_run", "arguments": "{}"})
        path, _ = tc_path(tc)
        assert path == "user.commands.run"

    def test_dispatch_after_tc_path(self):
        """Round-trip: LLM tool name → tc_path → dispatch_llm_tool → result."""
        # Register a test tool
        @llm_tool(name="roundtrip.test", description="Round-trip test")
        def rt_test(msg: str = "") -> dict:
            return {"success": True, "data": f"Got: {msg}"}

        tc = ToolCall(id="t5", function={"name": "roundtrip_test", "arguments": '{"msg": "hello"}'})
        path, flags = tc_path(tc)
        assert path == "roundtrip.test"
        result = dispatch_llm_tool(path, flags)
        assert result["success"] is True
        assert result["data"] == "Got: hello"

        _clear_registry()


# ═══════════════════════════════════════════════════════════════════════════════
# Email handler: email.find
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailFind:
    """Tests for the email.find LLM tool handler (mocked service)."""

    @patch("lighterbird.server.llm.tools.email.get_email_service")
    def test_basic_search(self, mock_get_svc):
        """email.find returns previews for search results."""
        mock_svc = MagicMock()
        mock_svc.search_messages.return_value = [
            {"uuid": "abc123", "subject": "Hello", "from_addr": "alice@test.com",
             "body": "This is a long body " * 100, "received_at": "2026-07-17T10:00:00"},
        ]
        mock_get_svc.return_value = mock_svc

        from lighterbird.server.llm.tools.email import llm_email_find
        result = llm_email_find(query="hello")

        assert result["success"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["subject"] == "Hello"
        assert "body_preview" in result["data"][0]  # body is truncated to body_preview
        assert "body" not in result["data"][0]  # full body removed from preview

    @patch("lighterbird.server.llm.tools.email.get_email_service")
    def test_search_with_date_filters(self, mock_get_svc):
        """ISO date params are parsed and passed as filters."""
        mock_svc = MagicMock()
        mock_svc.search_messages.return_value = []
        mock_get_svc.return_value = mock_svc

        from lighterbird.server.llm.tools.email import llm_email_find
        result = llm_email_find(after_date="2026-01-01", before_date="2026-12-31", max_results=10)

        assert result["success"] is True
        # Verify search_messages was called with after/before in filters
        call_kwargs = mock_svc.search_messages.call_args
        assert call_kwargs is not None
        filters = call_kwargs[0][0]
        assert "after" in filters
        assert "before" in filters

    @patch("lighterbird.server.llm.tools.email.get_email_service")
    def test_search_error(self, mock_get_svc):
        """Service exception is caught and returned as error."""
        mock_svc = MagicMock()
        mock_svc.search_messages.side_effect = RuntimeError("DB error")
        mock_get_svc.return_value = mock_svc

        from lighterbird.server.llm.tools.email import llm_email_find
        result = llm_email_find(query="test")

        assert result["success"] is False
        assert "DB error" in result["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# get_llm_tool_metadata
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetLlmToolMetadata:
    """Tests for get_llm_tool_metadata()."""

    def setup_method(self):
        _clear_registry()
        @llm_tool(
            name="meta.test",
            description="A test tool",
            params=[{"name": "x", "type": "string", "description": "Param X", "required": True}],
            permission_level=PermissionLevel.WRITE,
        )
        def meta_test(x: str = "") -> dict:
            return {"success": True, "data": x}

    def test_known_tool_returns_entry(self):
        """Known tool returns the full registry entry dict."""
        entry = get_llm_tool_metadata("meta.test")
        assert entry is not None
        assert entry["name"] == "meta_test"
        assert entry["description"] == "A test tool"
        assert entry["permission_level"] == PermissionLevel.WRITE
        assert entry["parameters"]["type"] == "object"
        assert "handler" in entry  # callable

    def test_unknown_tool_returns_none(self):
        """Unknown path returns None."""
        assert get_llm_tool_metadata("nonexistent") is None
        assert get_llm_tool_metadata("") is None

    def test_description_in_metadata(self):
        """Description is present and non-empty for known tools."""
        entry = get_llm_tool_metadata("meta.test")
        assert entry["description"] == "A test tool"

    def teardown_method(self):
        _clear_registry()


# ═══════════════════════════════════════════════════════════════════════════════
# All registered tools test
# ═══════════════════════════════════════════════════════════════════════════════


class TestAllRegisteredTools:
    """Integration test: all domain modules load and register their tools."""

    _TOOL_MODULES = [
        # lightercore bundled tools first (app modules below re-import from these)
        "lighterllm.llm.tools.system",
        # app-specific domain tool modules
        "lighterbird.server.llm.tools.system",
        "lighterbird.server.llm.tools.email",
        "lighterbird.server.llm.tools.calendar",
        "lighterbird.server.llm.tools.contacts",
        "lighterbird.server.llm.tools.todo",
        "lighterbird.server.llm.tools.journal",
        "lighterbird.server.llm.tools.letter",
    ]

    @pytest.fixture(autouse=True)
    def _load_all_tools(self):
        """Reload all domain modules to register their tools.

        Uses importlib.reload() because the modules may already be cached
        in sys.modules from previous tests — simple import would be a no-op.
        """
        import importlib
        _clear_registry()
        for mod_name in self._TOOL_MODULES:
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)
        yield

    def test_all_tools_registered(self):
        """All expected tools are registered."""
        names = get_llm_tool_names()
        expected = {
            "system.now",
            "email.find", "email.read", "email.send", "email.reply",
            "email.forward", "email.draft", "email.trash", "email.archive",
            "email.accounts.find", "email.accounts.read",
            "email.accounts.create", "email.accounts.update", "email.accounts.delete",
            "calendar.find", "calendar.read", "calendar.create",
            "calendar.update", "calendar.delete",
            "calendar.accounts.find", "calendar.accounts.read",
            "calendar.accounts.create", "calendar.accounts.update",
            "calendar.accounts.delete",
            "contacts.find", "contacts.read", "contacts.create",
            "contacts.update", "contacts.delete",
            "todo.find", "todo.read", "todo.create", "todo.update",
            "todo.done", "todo.delete",
            "journal.find", "journal.read", "journal.create", "journal.delete",
            "letter.find", "letter.read", "letter.create", "letter.update", "letter.delete",
        }
        missing = expected - set(names)
        extra = set(names) - expected
        assert not missing, f"Missing tools: {missing}"
        assert not extra, f"Unexpected tools: {extra}"
        assert len(names) == len(expected)

    def test_all_tools_have_openai_format(self):
        """All tools produce valid OpenAI function-calling definitions."""
        tools = get_llm_tools()
        for t in tools:
            assert t["type"] == "function"
            fn = t["function"]
            assert "name" in fn
            assert "description" in fn
            assert fn["name"].count("_") >= 1  # at least one underscore
            # Verify tc_path round-trip
            tc = ToolCall(id="t", function={"name": fn["name"], "arguments": "{}"})
            path, _ = tc_path(tc)
            assert path.replace(".", "_") == fn["name"]

    def test_permission_levels_are_valid(self):
        """All tools have valid permission levels."""
        for name in get_llm_tool_names():
            level = get_llm_tool_level(name)
            assert level is not None, f"{name} has no permission level"
            assert isinstance(level, PermissionLevel)

    def test_openai_tool_count(self):
        """Verify the total count of registered tools."""
        tools = get_llm_tools()
        # 1 + 13 + 10 + 5 + 6 + 4 + 5 = 44
        assert len(tools) == 44, f"Expected 44 tools, got {len(tools)}"

    def teardown_method(self):
        _clear_registry()
