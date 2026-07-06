"""Tests for drafts REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestDraftsAPI:
    """Test /api/v1/drafts endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_list_drafts_empty(self):
        """GET /api/v1/drafts returns empty list."""
        resp = self._client().get("/api/v1/drafts")
        assert resp.status_code == 200
        data = resp.json()
        assert "drafts" in data
        assert data["drafts"] == []

    def test_create_draft(self):
        """POST /api/v1/drafts creates a draft."""
        resp = self._client().post(
            "/api/v1/drafts",
            json={
                "domain": "email",
                "title": "Draft email",
                "data": {"to": "test@example.com", "subject": "Hello"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "email"
        assert "uuid" in data

    def test_create_and_get(self):
        """Create a draft then retrieve it by UUID."""
        client = self._client()
        created = client.post(
            "/api/v1/drafts",
            json={"domain": "journal", "title": "Morning notes", "data": {"text": "Woke up early"}},
        ).json()
        uuid = created["uuid"]

        resp = client.get(f"/api/v1/drafts/{uuid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Morning notes"

    def test_get_nonexistent_returns_404(self):
        """GET /api/v1/drafts/{uuid} with unknown UUID returns 404."""
        resp = self._client().get("/api/v1/drafts/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_delete_draft(self):
        """DELETE /api/v1/drafts/{uuid} deletes a draft."""
        client = self._client()
        created = client.post(
            "/api/v1/drafts",
            json={"domain": "todo", "title": "Buy milk", "data": {"priority": 3}},
        ).json()
        uuid = created["uuid"]

        resp = client.delete(f"/api/v1/drafts/{uuid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_delete_nonexistent_returns_404(self):
        """DELETE /api/v1/drafts/{uuid} with unknown UUID returns 404."""
        resp = self._client().delete("/api/v1/drafts/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_invalid_domain_rejected(self):
        """POST /api/v1/drafts with invalid domain returns 422."""
        resp = self._client().post(
            "/api/v1/drafts",
            json={"domain": "invalid", "title": "Test", "data": {}},
        )
        assert resp.status_code == 422
