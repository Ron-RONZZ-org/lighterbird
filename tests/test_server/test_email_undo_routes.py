"""Tests for the email undo REST API routes.

Tests that ``POST /api/v1/email/actions/undo/{op_id}`` works correctly
with a real UndoRegistry.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from lighterbird.email.undo import get_undo_registry, reset_undo_registry


@pytest.fixture(autouse=True)
def clean_registry():
    """Reset the undo registry before and after each test."""
    reset_undo_registry()
    yield
    reset_undo_registry()


@pytest.fixture
def client():
    """Create a test client with minimal app that only has the undo router."""
    from fastapi import FastAPI
    from lighterbird.server.routes.email_undo import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestUndoRoutes:
    """Tests for the undo HTTP endpoint."""

    def test_undo_success(self, client):
        """Undoing a pending operation succeeds."""
        registry = get_undo_registry()

        op_id = registry.schedule(
            action="trash", msg_uuid="test-uuid", account_email="a@b.com",
            folder_name="INBOX", imap_uid=123, delay=5.0,
        )
        registry.set_callbacks(
            op_id,
            revert_cb=lambda: None,
            commit_cb=lambda: None,
        )

        resp = client.post(f"/api/v1/email/actions/undo/{op_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reverted"
        assert data["operation_id"] == op_id

    def test_undo_nonexistent_returns_409(self, client):
        """Undoing a non-existent operation returns 409."""
        resp = client.post("/api/v1/email/actions/undo/nonexistent-op-id")
        assert resp.status_code == 409
        assert "detail" in resp.json()

    def test_undo_after_commit_returns_409(self, client):
        """Undoing an already-committed operation returns 409."""
        registry = get_undo_registry()

        op_id = registry.schedule(
            action="trash", msg_uuid="test-uuid", account_email="a@b.com",
            folder_name="INBOX", imap_uid=123, delay=0.02,
        )

        committed = []
        registry.set_callbacks(
            op_id,
            revert_cb=lambda: None,
            commit_cb=lambda: committed.append(True),
        )

        time.sleep(0.1)
        assert committed == [True]

        resp = client.post(f"/api/v1/email/actions/undo/{op_id}")
        assert resp.status_code == 409
