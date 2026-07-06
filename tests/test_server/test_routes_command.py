"""Tests for command REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestCommandAPI:
    """Test /api/v1/command endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_get_command_tree(self):
        """GET /api/v1/command/tree returns command tree."""
        resp = self._client().get("/api/v1/command/tree")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_command_definitions(self):
        """GET /api/v1/command/definitions returns definitions."""
        resp = self._client().get("/api/v1/command/definitions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_execute_unknown_command(self):
        """POST /api/v1/command with unknown tokens returns 400."""
        resp = self._client().post(
            "/api/v1/command",
            json={"tokens": ["!nonexistent"]},
        )
        assert resp.status_code == 400

    def test_execute_help_command(self):
        """POST /api/v1/command with help returns help response."""
        resp = self._client().post(
            "/api/v1/command",
            json={"tokens": ["help"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "help"

    def test_execute_todo_list(self):
        """POST /api/v1/command with todo list returns todo-list response."""
        resp = self._client().post(
            "/api/v1/command",
            json={"tokens": ["todo", "list"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "type" in data

    def test_execute_with_form_flag(self):
        """POST /api/v1/command with --form flag returns form-required."""
        resp = self._client().post(
            "/api/v1/command",
            json={"tokens": ["email", "send"], "flags": {"form": "true"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "form-required"
