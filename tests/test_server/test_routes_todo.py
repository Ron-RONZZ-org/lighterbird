"""Tests for todo REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestTodoAPI:
    """Test /api/v1/todo/todos endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_list_todos_empty(self):
        """GET /api/v1/todo/todos returns empty list."""
        resp = self._client().get("/api/v1/todo/todos")
        assert resp.status_code == 200
        data = resp.json()
        assert "todos" in data
        assert data["todos"] == []

    def test_create_todo(self):
        """POST /api/v1/todo/todos creates a todo."""
        resp = self._client().post("/api/v1/todo/todos", json={"title": "Buy milk"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Buy milk"
        assert "uuid" in data

    def test_create_and_get(self):
        """Create a todo then retrieve it by UUID."""
        client = self._client()
        created = client.post("/api/v1/todo/todos", json={"title": "Write tests"}).json()
        uuid = created["uuid"]

        resp = client.get(f"/api/v1/todo/todos/{uuid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Write tests"

    def test_get_nonexistent_returns_404(self):
        """GET with unknown UUID returns 404."""
        resp = self._client().get("/api/v1/todo/todos/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_update_todo(self):
        """PATCH /api/v1/todo/todos/{uuid} updates fields."""
        client = self._client()
        created = client.post("/api/v1/todo/todos", json={"title": "Old title", "priority": 5}).json()
        uuid = created["uuid"]

        resp = client.patch(
            f"/api/v1/todo/todos/{uuid}",
            json={"title": "New title", "priority": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New title"
        assert resp.json()["priority"] in (1, "1")

    def test_delete_todo(self):
        """DELETE /api/v1/todo/todos/{uuid} returns 204."""
        client = self._client()
        created = client.post("/api/v1/todo/todos", json={"title": "Delete me"}).json()
        uuid = created["uuid"]

        resp = client.delete(f"/api/v1/todo/todos/{uuid}")
        assert resp.status_code == 204

        # Verify deletion
        assert client.get(f"/api/v1/todo/todos/{uuid}").status_code == 404

    def test_tree_view(self):
        """GET /api/v1/todo/todos?tree=true returns tree."""
        client = self._client()
        client.post("/api/v1/todo/todos", json={"title": "Root task"})
        resp = client.get("/api/v1/todo/todos", params={"tree": "true"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tree"] is True
        assert "todos" in data

    def test_mark_done(self):
        """POST /api/v1/todo/todos/{uuid}/done marks as done."""
        client = self._client()
        created = client.post("/api/v1/todo/todos", json={"title": "Finish task"}).json()
        uuid = created["uuid"]

        resp = client.post(f"/api/v1/todo/todos/{uuid}/done")
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"
