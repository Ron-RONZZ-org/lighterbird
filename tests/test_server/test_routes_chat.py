"""Tests for chat REST API routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from lightercore.permissions import PermissionLevel

from lighterbird.server.app import create_app


class TestChatAPIDispatchAndMetadata:
    """Unit tests for the dispatch, permission, and metadata callbacks
    used by /api/v1/chat to interact with the LLM tool registry."""

    # ── _dispatch_llm_tool ─────────────────────────────────────────────────

    def test_dispatch_llm_tool_wrapper(self):
        """_dispatch_llm_tool routes to dispatch_llm_tool."""
        from lighterbird.server.routes.chat import _dispatch_llm_tool
        from lighterbird.server.llm.tools import dispatch_llm_tool

        with patch(
            "lighterbird.server.routes.chat.dispatch_llm_tool",
            return_value={"success": True, "data": "mocked"},
        ) as mock_dispatch:
            result = _dispatch_llm_tool("email.find", {"query": "test"})
            assert result == {"success": True, "data": "mocked"}
            mock_dispatch.assert_called_once_with("email.find", {"query": "test"})

    # ── _get_llm_tool_level ────────────────────────────────────────────────

    def test_get_llm_tool_level_wrapper(self):
        """_get_llm_tool_level routes to get_llm_tool_level."""
        from lighterbird.server.routes.chat import _get_llm_tool_level
        from lighterbird.server.llm.tools import get_llm_tool_level

        with patch(
            "lighterbird.server.routes.chat.get_llm_tool_level",
            return_value=PermissionLevel.READ,
        ) as mock_level:
            result = _get_llm_tool_level("system.now")
            assert result == PermissionLevel.READ
            mock_level.assert_called_once_with("system.now")

    # ── _get_handler_metadata (combined lookup) ────────────────────────────

    def test_get_handler_metadata_llm_tool_first(self):
        """Combined metadata lookup returns LLM tool entry first."""
        from lighterbird.server.routes.chat import _get_handler_metadata

        with patch(
            "lighterbird.server.routes.chat.get_llm_tool_metadata",
            return_value={"name": "email_find", "description": "Search emails"},
        ) as mock_llm_meta:
            result = _get_handler_metadata("email.find")
            assert result == {"name": "email_find", "description": "Search emails"}
            mock_llm_meta.assert_called_once_with("email.find")

    def test_get_handler_metadata_falls_back_to_cli(self):
        """Combined metadata falls back to CLI registry when LLM tool unknown."""
        from lighterbird.server.routes.chat import _get_handler_metadata

        with patch(
            "lighterbird.server.routes.chat.get_llm_tool_metadata",
            return_value=None,
        ), patch(
            "lighterbird.server.routes.chat._get_cli_handler_metadata",
            return_value={"description": "CLI command"},
        ) as mock_cli:
            result = _get_handler_metadata("email.list")
            assert result == {"description": "CLI command"}
            mock_cli.assert_called_once_with("email.list")

    def test_get_handler_metadata_unknown_returns_none(self):
        """Combined metadata returns None when neither registry has the path."""
        from lighterbird.server.routes.chat import _get_handler_metadata

        with patch(
            "lighterbird.server.routes.chat.get_llm_tool_metadata",
            return_value=None,
        ), patch(
            "lighterbird.server.routes.chat._get_cli_handler_metadata",
            return_value=None,
        ):
            result = _get_handler_metadata("completely.unknown")
            assert result is None


class TestChatAPI:
    """Test /api/v1/chat endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_chat_missing_message_returns_400(self):
        """POST /api/v1/chat without message returns 400."""
        resp = self._client().post("/api/v1/chat", json={})
        assert resp.status_code == 400
        data = resp.json()
        assert "detail" in data

    def test_chat_empty_message_returns_400(self):
        """POST /api/v1/chat with empty message returns 400."""
        resp = self._client().post("/api/v1/chat", json={"message": ""})
        assert resp.status_code == 400

    def test_chat_no_llm_returns_status(self):
        """POST /api/v1/chat without LLM configured returns status message."""
        from lighterbird.server.llm.provider import get_provider as get_llm_provider

        with patch.object(
            get_llm_provider(), "is_available", return_value=False
        ):
            resp = self._client().post("/api/v1/chat", json={"message": "Hello"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["type"] == "status"
            assert "not configured" in data["data"]["message"].lower()

    def test_chat_uses_llm_tools_not_cli_defs(self):
        """chat_endpoint calls get_llm_tools() instead of get_definitions().

        Mock get_llm_tools to return a sentinel value and verify it's
        called.  Also mock the provider so the tool loop is reachable.
        """
        from lighterbird.server.llm.provider import get_provider as get_llm_provider

        with patch.object(
            get_llm_provider(), "is_available", return_value=True
        ), patch(
            "lighterbird.server.routes.chat.get_llm_tools",
            return_value=[{"type": "function", "function": {"name": "test_tool"}}],
        ) as mock_get_tools, patch(
            "lighterbird.server.routes.chat.run_tool_loop",
        ) as mock_loop:
            # Mock run_tool_loop to return a result so the endpoint doesn't hang
            mock_loop.return_value = "Mock reply"

            resp = self._client().post("/api/v1/chat", json={"message": "Hi"})
            assert resp.status_code == 200

            # Verify get_llm_tools was called (not get_definitions)
            mock_get_tools.assert_called_once()

            # Verify run_tool_loop was called with LLM tools
            call_args, call_kwargs = mock_loop.call_args
            assert call_kwargs["tools"] == [
                {"type": "function", "function": {"name": "test_tool"}}
            ]
            # Verify dispatch and permission callbacks
            assert call_kwargs["dispatch_fn"] is not None
            assert call_kwargs["get_tool_level_fn"] is not None

    def test_chat_resume_uses_llm_tools_callbacks(self):
        """chat_resume passes LLM tool callbacks to resume_execution."""
        from lighterbird.server.llm.provider import get_provider as get_llm_provider

        with patch.object(
            get_llm_provider(), "is_available", return_value=True
        ), patch(
            "lighterbird.server.routes.chat.resume_execution",
            return_value="Resumed reply",
        ) as mock_resume:
            resp = self._client().post("/api/v1/chat/resume", json={
                "session_id": "test-session",
                "confirmed": True,
            })
            assert resp.status_code == 200

            # Verify resume_execution was called with LLM tool callbacks
            _, call_kwargs = mock_resume.call_args
            assert call_kwargs["dispatch_fn"] is not None
            assert call_kwargs["get_handler_metadata_fn"] is not None
            assert call_kwargs["get_tool_level_fn"] is not None
            assert call_kwargs["session_id"] == "test-session"

    def test_chat_notice_endpoint(self):
        """GET /api/v1/chat/notice returns notice info."""
        resp = self._client().get("/api/v1/chat/notice")
        assert resp.status_code == 200
        data = resp.json()
        assert "notice" in data
