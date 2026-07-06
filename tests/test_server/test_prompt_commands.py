"""Tests for server/routes/prompt_commands.py — prompt commands API.

These tests use a mock commands directory to avoid touching real config.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lighterbird.server.app import create_app
from lighterbird.server.deps import reset_services


@pytest.fixture
def client(tmp_path: Path):
    """Create a TestClient with isolated config directory."""
    reset_services()
    app = create_app()

    # Override config_dir so prompt-commands routes scan tmp_path/commands/
    import lightercore.paths as lc_paths
    original_config_dir = lc_paths.config_dir

    def _mock_config_dir() -> Path:
        return tmp_path

    lc_paths.config_dir = _mock_config_dir  # type: ignore[assignment]

    # Ensure commands dir exists
    (tmp_path / "commands").mkdir(exist_ok=True)

    yield TestClient(app)

    # Restore
    lc_paths.config_dir = original_config_dir


# ── Helpers ───────────────────────────────────────────────────────────────────


def create_command(tmp_path: Path, name: str, description: str, template: str) -> Path:
    """Create a prompt command .md file for testing."""
    path = tmp_path / "commands" / f"{name}.md"
    path.write_text(f"# {description}\n{template}", encoding="utf-8")
    return path


class TestListEndpoint:
    """GET /api/v1/prompt-commands/list"""

    def test_empty_dir(self, client, tmp_path):
        resp = client.get("/api/v1/prompt-commands/list")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_commands(self, client, tmp_path):
        create_command(tmp_path, "weekly", "Weekly report", "Compile $1 report.")
        create_command(tmp_path, "summarize", "Summarize emails", "Summarize $1 emails in $2.")
        resp = client.get("/api/v1/prompt-commands/list")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "summarize"
        assert data[0]["description"] == "Summarize emails"
        assert data[0]["param_count"] == 2
        assert data[1]["name"] == "weekly"

    def test_skips_invalid_files(self, client, tmp_path):
        (tmp_path / "commands" / "notes.txt").write_text("# Not an md", encoding="utf-8")
        resp = client.get("/api/v1/prompt-commands/list")
        assert resp.json() == []


class TestExpandEndpoint:
    """POST /api/v1/prompt-commands/expand"""

    def test_expand_with_args(self, client, tmp_path):
        create_command(tmp_path, "test", "Test command", "Hello $1 from $2!")
        resp = client.post("/api/v1/prompt-commands/expand", json={
            "name": "test",
            "args": ["World", "lighterbird"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test"
        assert data["description"] == "Test command"
        assert data["expanded"] == "Hello World from lighterbird!"
        assert data["param_count"] == 2

    def test_no_args(self, client, tmp_path):
        create_command(tmp_path, "static", "Static", "Hello world!")
        resp = client.post("/api/v1/prompt-commands/expand", json={
            "name": "static",
            "args": [],
        })
        assert resp.status_code == 200
        assert resp.json()["expanded"] == "Hello world!"

    def test_name_required(self, client, tmp_path):
        resp = client.post("/api/v1/prompt-commands/expand", json={"args": []})
        assert resp.status_code == 400
        assert "name" in resp.json()["detail"].lower()

    def test_not_found(self, client, tmp_path):
        resp = client.post("/api/v1/prompt-commands/expand", json={
            "name": "nonexistent",
            "args": [],
        })
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_case_insensitive_name(self, client, tmp_path):
        create_command(tmp_path, "MyCmd", "Case test", "body $1")
        resp = client.post("/api/v1/prompt-commands/expand", json={
            "name": "mycmd",
            "args": ["arg"],
        })
        assert resp.status_code == 200
        assert resp.json()["expanded"] == "body arg"


class TestExecuteEndpoint:
    """POST /api/v1/prompt-commands/execute"""

    def test_llm_not_configured(self, client, tmp_path):
        """Should return a status message, not error, when no LLM provider."""
        create_command(tmp_path, "test", "Test", "Hello $1!")
        resp = client.post("/api/v1/prompt-commands/execute", json={
            "name": "test",
            "args": ["World"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "status"
        # Should mention LLM not configured
        msg = data["data"]["message"].lower()
        assert "llm" in msg
        assert "not configured" in msg or "configure" in msg

    def test_not_found(self, client, tmp_path):
        resp = client.post("/api/v1/prompt-commands/execute", json={
            "name": "nonexistent",
            "args": [],
        })
        assert resp.status_code == 404

    def test_name_required(self, client, tmp_path):
        resp = client.post("/api/v1/prompt-commands/execute", json={"args": []})
        assert resp.status_code == 400


class TestExecuteStreamEndpoint:
    """POST /api/v1/prompt-commands/execute/stream"""

    def test_not_found_returns_sse(self, client, tmp_path):
        resp = client.post("/api/v1/prompt-commands/execute/stream", json={
            "name": "nonexistent",
            "args": [],
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
        body = resp.text
        assert "not found" in body.lower()
        assert "[DONE]" in body

    def test_llm_not_configured_returns_sse(self, client, tmp_path):
        create_command(tmp_path, "test", "Test", "Hello $1!")
        resp = client.post("/api/v1/prompt-commands/execute/stream", json={
            "name": "test",
            "args": ["World"],
        })
        assert resp.status_code == 200
        body = resp.text
        assert "llm" in body.lower() or "not configured" in body.lower()
        assert "[DONE]" in body

    def test_name_required(self, client, tmp_path):
        resp = client.post("/api/v1/prompt-commands/execute/stream", json={"args": []})
        assert resp.status_code == 400
