"""Tests for admin REST API routes — health, sync."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestAdminAPI:
    """Test /api/v1 admin endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_health(self):
        """GET /api/v1/health returns ok status."""
        resp = self._client().get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.2.0"

    def test_sync_all(self):
        """POST /api/v1/sync/all triggers sync."""
        resp = self._client().post("/api/v1/sync/all")
        assert resp.status_code == 200
        data = resp.json()
        assert "email" in data
        assert "calendar" in data
