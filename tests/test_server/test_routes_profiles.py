"""Tests for profiles REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestProfilesAPI:
    """Test /api/v1/profiles/profiles endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_list_profiles(self):
        """GET /api/v1/profiles/profiles returns profile list."""
        resp = self._client().get("/api/v1/profiles/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data
        assert "total" in data

    def test_get_nonexistent_returns_404(self):
        """GET with unknown UUID returns 404."""
        resp = self._client().get("/api/v1/profiles/profiles/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
