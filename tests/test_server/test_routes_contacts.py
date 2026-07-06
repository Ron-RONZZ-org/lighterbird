"""Tests for contacts REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestContactsAPI:
    """Test /api/v1/contacts endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_list_empty(self):
        """GET /api/v1/contacts/contacts returns empty list."""
        resp = self._client().get("/api/v1/contacts/contacts")
        assert resp.status_code == 200
        data = resp.json()
        assert "contacts" in data
        assert data["contacts"] == []

    def test_create_contact(self):
        """POST /api/v1/contacts/contacts creates a contact."""
        resp = self._client().post(
            "/api/v1/contacts/contacts",
            json={"name": "Alice", "email": "alice@example.com"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["full_name"] == "Alice"
        assert "uuid" in data

    def test_create_and_get(self):
        """Create a contact then retrieve it by UUID."""
        client = self._client()
        created = client.post(
            "/api/v1/contacts/contacts",
            json={"name": "Bob", "email": "bob@example.com"},
        ).json()
        uuid = created["uuid"]

        resp = client.get(f"/api/v1/contacts/contacts/{uuid}")
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Bob"

    def test_get_nonexistent_returns_404(self):
        """GET with an unknown UUID returns 404."""
        resp = self._client().get("/api/v1/contacts/contacts/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_search_by_name(self):
        """GET with ?search=... filters contacts."""
        client = self._client()
        client.post(
            "/api/v1/contacts/contacts",
            json={"name": "Charlie", "organization": "Acme"},
        )
        client.post(
            "/api/v1/contacts/contacts",
            json={"name": "Diana", "organization": "Beta"},
        )
        resp = client.get("/api/v1/contacts/contacts", params={"query": "Charlie"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["contacts"]) == 1
        assert data["contacts"][0]["full_name"] == "Charlie"

    def test_update_contact(self):
        """PATCH /api/v1/contacts/contacts/{uuid} updates fields."""
        client = self._client()
        created = client.post(
            "/api/v1/contacts/contacts",
            json={"name": "Eve", "organization": "OldCorp"},
        ).json()
        uuid = created["uuid"]

        resp = client.patch(
            f"/api/v1/contacts/contacts/{uuid}",
            json={"organization": "NewCorp", "notes": "Updated"},
        )
        assert resp.status_code == 200
        updated = client.get(f"/api/v1/contacts/contacts/{uuid}").json()
        assert updated["organization"] == "NewCorp"

    def test_delete_contact(self):
        """DELETE /api/v1/contacts/contacts/{uuid} returns 204."""
        client = self._client()
        created = client.post(
            "/api/v1/contacts/contacts",
            json={"name": "Frank"},
        ).json()
        uuid = created["uuid"]

        resp = client.delete(f"/api/v1/contacts/contacts/{uuid}")
        assert resp.status_code == 204

        # Verify deletion
        assert client.get(f"/api/v1/contacts/contacts/{uuid}").status_code == 404
