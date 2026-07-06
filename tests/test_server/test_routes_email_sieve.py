"""Tests for Sieve script REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestEmailSieveAPI:
    """Test /api/v1/email/sieve/scripts endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_list_scripts_empty(self):
        """GET /api/v1/email/sieve/scripts returns empty list."""
        resp = self._client().get("/api/v1/email/sieve/scripts")
        assert resp.status_code == 200
        data = resp.json()
        assert "scripts" in data

    def test_create_script(self):
        """POST /api/v1/email/sieve/scripts creates a script."""
        resp = self._client().post(
            "/api/v1/email/sieve/scripts",
            json={"name": "myfilter", "content": "require [\"fileinto\"];\nfileinto \"INBOX\";"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "myfilter"
        assert "content" in data

    def test_create_and_get(self):
        """Create a script then retrieve it by name."""
        client = self._client()
        post_resp = client.post(
            "/api/v1/email/sieve/scripts",
            json={"name": "myfilter", "content": "require [\"fileinto\"];\nfileinto \"INBOX\";"},
        )
        assert post_resp.status_code == 201

        resp = client.get("/api/v1/email/sieve/scripts/myfilter")
        assert resp.status_code == 200
        assert resp.json()["name"] == "myfilter"

    def test_get_nonexistent_returns_404(self):
        """GET /api/v1/email/sieve/scripts/{name} with unknown name returns 404."""
        resp = self._client().get("/api/v1/email/sieve/scripts/nonexistent")
        assert resp.status_code == 404

    def test_update_script(self):
        """PATCH /api/v1/email/sieve/scripts/{name} updates content."""
        client = self._client()
        post_resp = client.post(
            "/api/v1/email/sieve/scripts",
            json={"name": "update_test", "content": "keep;"},
        )
        assert post_resp.status_code == 201

        resp = client.patch(
            "/api/v1/email/sieve/scripts/update_test",
            json={"content": "discard;"},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "discard;"

    def test_delete_script(self):
        """DELETE /api/v1/email/sieve/scripts/{name} deletes a script."""
        client = self._client()
        client.post(
            "/api/v1/email/sieve/scripts",
            json={"name": "todelete", "content": "keep;"},
        )

        resp = client.delete("/api/v1/email/sieve/scripts/todelete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_nonexistent_returns_404(self):
        """DELETE /api/v1/email/sieve/scripts/{name} with unknown name returns 404."""
        resp = self._client().delete("/api/v1/email/sieve/scripts/nonexistent")
        assert resp.status_code == 404

    def test_validate_script(self):
        """POST /api/v1/email/sieve/validate validates a script."""
        resp = self._client().post(
            "/api/v1/email/sieve/validate",
            json={"content": "require [\"fileinto\"];\nfileinto \"INBOX\";"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "is_valid" in data

    def test_analyze_scripts(self):
        """POST /api/v1/email/sieve/analyze analyzes scripts."""
        resp = self._client().post(
            "/api/v1/email/sieve/analyze",
            json={"scripts": [{"name": "a", "content": "keep;"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "combined" in data
