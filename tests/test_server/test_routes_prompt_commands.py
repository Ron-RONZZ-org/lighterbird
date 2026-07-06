"""Tests for prompt commands REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestPromptCommandsAPI:
    """Test /api/v1/prompt-commands endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_list_commands(self):
        """GET /api/v1/prompt-commands/list returns empty list."""
        resp = self._client().get("/api/v1/prompt-commands/list")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_expand_missing_name(self):
        """POST /api/v1/prompt-commands/expand without name returns 400."""
        resp = self._client().post(
            "/api/v1/prompt-commands/expand",
            json={"args": ["INBOX"]},
        )
        assert resp.status_code == 400
        assert "name" in resp.text.lower()

    def test_expand_unknown_command(self):
        """POST /api/v1/prompt-commands/expand with unknown name returns 404."""
        resp = self._client().post(
            "/api/v1/prompt-commands/expand",
            json={"name": "nonexistent-command"},
        )
        assert resp.status_code == 404

    def test_execute_missing_name(self):
        """POST /api/v1/prompt-commands/execute without name returns 400."""
        resp = self._client().post(
            "/api/v1/prompt-commands/execute",
            json={"args": ["INBOX"]},
        )
        assert resp.status_code == 400

    def test_execute_unknown_command(self):
        """POST /api/v1/prompt-commands/execute with unknown name returns 404."""
        resp = self._client().post(
            "/api/v1/prompt-commands/execute",
            json={"name": "nonexistent-command"},
        )
        assert resp.status_code == 404
