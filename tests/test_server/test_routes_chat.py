"""Tests for chat REST API routes."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


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

    def test_chat_notice_endpoint(self):
        """GET /api/v1/chat/notice returns notice info."""
        resp = self._client().get("/api/v1/chat/notice")
        assert resp.status_code == 200
        data = resp.json()
        assert "notice" in data
