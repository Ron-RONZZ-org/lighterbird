"""Tests for tags REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestTagsAPI:
    """Test /api/v1/tags endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_list_tags_empty(self):
        """GET /api/v1/tags returns empty list."""
        resp = self._client().get("/api/v1/tags")
        assert resp.status_code == 200
        data = resp.json()
        assert "tags" in data
        assert data["tags"] == []

    def test_autocomplete_empty(self):
        """GET /api/v1/tags/autocomplete returns empty list."""
        resp = self._client().get("/api/v1/tags/autocomplete", params={"q": "work"})
        assert resp.status_code == 200
        data = resp.json()
        assert "tags" in data

    def test_domain_tags_empty(self):
        """GET /api/v1/tags/domain/{domain} returns tags for empty domain."""
        resp = self._client().get("/api/v1/tags/domain/todo")
        assert resp.status_code == 200
        data = resp.json()
        assert "tags" in data
        assert data["count"] == 0
