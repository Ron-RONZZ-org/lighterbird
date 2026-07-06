"""Tests for email REST API routes — messages, folders, views."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestEmailMessagesAPI:
    """Test /api/v1/email endpoints for messages and folders."""

    def _client(self):
        return TestClient(create_app())

    def test_list_messages_empty(self):
        """GET /api/v1/email/messages returns empty list."""
        resp = self._client().get("/api/v1/email/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert data["messages"] == []

    def test_get_message_nonexistent_returns_404(self):
        """GET /api/v1/email/messages/{uuid} with unknown UUID returns 404."""
        resp = self._client().get(
            "/api/v1/email/messages/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404

    def test_list_folders_empty(self):
        """GET /api/v1/email/folders returns empty list."""
        resp = self._client().get("/api/v1/email/folders")
        assert resp.status_code == 200
        data = resp.json()
        assert "folders" in data

    def test_get_message_conversation_nonexistent(self):
        """GET /api/v1/email/messages/{uuid}/conversation returns empty."""
        resp = self._client().get(
            "/api/v1/email/messages/00000000-0000-0000-0000-000000000000/conversation"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
