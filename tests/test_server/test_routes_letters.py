"""Tests for letters REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestLettersAPI:
    """Test /api/v1/letters/letters endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_list_letters_empty(self):
        """GET /api/v1/letters/letters returns empty list."""
        resp = self._client().get("/api/v1/letters/letters")
        assert resp.status_code == 200
        data = resp.json()
        assert "letters" in data
        assert data["letters"] == []

    def test_create_letter(self):
        """POST /api/v1/letters/letters creates a letter."""
        resp = self._client().post(
            "/api/v1/letters/letters",
            json={
                "direction": "sent",
                "object": "Hello",
                "sender_manual": "Alice",
                "recipient_manual": "Bob",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["object"] == "Hello"
        assert "uuid" in data

    def test_create_and_get(self):
        """Create a letter then retrieve it by UUID."""
        client = self._client()
        created = client.post(
            "/api/v1/letters/letters",
            json={"direction": "received", "object": "Greetings", "sender_manual": "Carol"},
        ).json()
        uuid = created["uuid"]

        resp = client.get(f"/api/v1/letters/letters/{uuid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "Greetings"

    def test_get_nonexistent_returns_404(self):
        """GET with unknown UUID returns 404."""
        resp = self._client().get("/api/v1/letters/letters/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_get_letter_body(self):
        """GET /api/v1/letters/letters/{uuid}/body returns body."""
        client = self._client()
        created = client.post(
            "/api/v1/letters/letters",
            json={
                "direction": "sent",
                "object": "With Body",
                "sender_manual": "Me",
                "recipient_manual": "You",
                "body": "<p>Hello World</p>",
                "body_format": "html",
            },
        ).json()
        uuid = created["uuid"]

        resp = client.get(f"/api/v1/letters/letters/{uuid}/body")
        assert resp.status_code == 200
        data = resp.json()
        assert data["uuid"] == uuid
        assert "body" in data

    def test_render_preview(self):
        """POST /api/v1/letters/render-preview converts markdown to HTML."""
        resp = self._client().post(
            "/api/v1/letters/render-preview",
            json={"content": "**bold** text", "format": "markdown"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "<strong>" in data["html"] or "<b>" in data["html"].lower() or "bold" in data["html"]

    def test_delete_letter(self):
        """DELETE /api/v1/letters/letters/{uuid} returns 204."""
        client = self._client()
        created = client.post(
            "/api/v1/letters/letters",
            json={"direction": "received", "object": "Delete Me", "sender_manual": "Spammer"},
        ).json()
        uuid = created["uuid"]

        resp = client.delete(f"/api/v1/letters/letters/{uuid}")
        assert resp.status_code == 204

        # Verify deletion
        assert client.get(f"/api/v1/letters/letters/{uuid}").status_code == 404
