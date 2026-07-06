"""Tests for LLM configuration REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestLLMAPI:
    """Test /api/v1/llm endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_get_config(self):
        """GET /api/v1/llm/config returns default config."""
        resp = self._client().get("/api/v1/llm/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "provider_type" in data
        assert "available" in data

    def test_reset_config(self):
        """POST /api/v1/llm/reset clears config."""
        resp = self._client().post("/api/v1/llm/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_configure_llm(self):
        """POST /api/v1/llm/configure sets provider."""
        resp = self._client().post(
            "/api/v1/llm/configure",
            json={"provider_type": "openai", "api_key": "sk-test", "model": "gpt-4"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "openai"

    def test_get_prompt(self):
        """GET /api/v1/llm/prompt returns system prompt."""
        resp = self._client().get("/api/v1/llm/prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert "prompt" in data
        assert "path" in data

    def test_reload_prompt(self):
        """POST /api/v1/llm/reload-prompt reloads the prompt."""
        resp = self._client().post("/api/v1/llm/reload-prompt")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_list_profiles_empty(self):
        """GET /api/v1/llm/profiles returns empty list."""
        resp = self._client().get("/api/v1/llm/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data

    def test_create_and_get_profile(self):
        """POST then GET /api/v1/llm/profiles/{name}."""
        client = self._client()
        client.post(
            "/api/v1/llm/profiles",
            json={
                "name": "test-profile",
                "provider_type": "openai",
                "api_key": "sk-test",
                "model": "gpt-4",
                "base_url": "",
            },
        )

        resp = client.get("/api/v1/llm/profiles/test-profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-profile"
        assert data["has_api_key"] is True

    def test_get_profile_nonexistent_returns_404(self):
        """GET /api/v1/llm/profiles/{name} with unknown name returns 404."""
        resp = self._client().get("/api/v1/llm/profiles/nonexistent")
        assert resp.status_code == 404

    def test_delete_profile(self):
        """DELETE /api/v1/llm/profiles/{name} deletes a profile."""
        client = self._client()
        client.post(
            "/api/v1/llm/profiles",
            json={"name": "temp-profile", "provider_type": "openai"},
        )

        resp = client.delete("/api/v1/llm/profiles/temp-profile")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_load_nonexistent_profile_returns_404(self):
        """POST /api/v1/llm/profiles/{name}/load with unknown name returns 404."""
        resp = self._client().post("/api/v1/llm/profiles/nonexistent/load")
        assert resp.status_code == 404
