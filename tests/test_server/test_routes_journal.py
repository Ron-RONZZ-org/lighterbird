"""Tests for journal REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestJournalAPI:
    """Test /api/v1/journal/entries endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_list_entries_empty(self):
        """GET /api/v1/journal/entries returns empty list."""
        resp = self._client().get("/api/v1/journal/entries")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert data["entries"] == []

    def test_create_entry(self):
        """POST /api/v1/journal/entries creates an entry."""
        resp = self._client().post(
            "/api/v1/journal/entries",
            json={"title": "My Day", "text": "It was great."},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "My Day"
        assert "uuid" in data

    def test_create_and_get(self):
        """Create an entry then retrieve it by UUID."""
        client = self._client()
        created = client.post(
            "/api/v1/journal/entries",
            json={"title": "Notes", "text": "Some notes."},
        ).json()
        uuid = created["uuid"]

        resp = client.get(f"/api/v1/journal/entries/{uuid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Notes"

    def test_get_nonexistent_returns_404(self):
        """GET with unknown UUID returns 404."""
        resp = self._client().get("/api/v1/journal/entries/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_update_entry(self):
        """PATCH /api/v1/journal/entries/{uuid} updates fields."""
        client = self._client()
        created = client.post(
            "/api/v1/journal/entries",
            json={"title": "Draft", "text": "Old text"},
        ).json()
        uuid = created["uuid"]

        resp = client.patch(
            f"/api/v1/journal/entries/{uuid}",
            json={"title": "Final", "text": "Updated text"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Final"
        assert data["text"] == "Updated text"

    def test_delete_entry(self):
        """DELETE /api/v1/journal/entries/{uuid} returns 204."""
        client = self._client()
        created = client.post(
            "/api/v1/journal/entries",
            json={"title": "Temp", "text": "Will be deleted."},
        ).json()
        uuid = created["uuid"]

        resp = client.delete(f"/api/v1/journal/entries/{uuid}")
        assert resp.status_code == 204

        # Verify deletion
        assert client.get(f"/api/v1/journal/entries/{uuid}").status_code == 404

    def test_search_entries(self):
        """GET /api/v1/journal/entries?query=... filters entries."""
        client = self._client()
        client.post("/api/v1/journal/entries", json={"title": "Shopping", "text": "Buy groceries"})
        client.post("/api/v1/journal/entries", json={"title": "Work", "text": "Meeting notes"})

        resp = client.get("/api/v1/journal/entries", params={"query": "groceries"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["title"] == "Shopping"
