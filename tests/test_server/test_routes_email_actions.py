"""Tests for email action REST API routes — send, trash, batch ops."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestEmailActionsAPI:
    """Test /api/v1/email action endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_trash_nonexistent_message(self):
        """POST /api/v1/email/messages/{uuid}/trash on unknown UUID."""
        resp = self._client().post(
            "/api/v1/email/messages/00000000-0000-0000-0000-000000000000/trash"
        )
        # Trashing a nonexistent message may succeed or fail silently
        assert resp.status_code in (200, 404)

    def test_send_missing_required_fields(self):
        """POST /api/v1/email/send without required fields returns 422."""
        resp = self._client().post("/api/v1/email/send", json={})
        assert resp.status_code == 422

    def test_send_with_extra_fields_rejected(self):
        """POST /api/v1/email/send with unknown fields returns 422."""
        resp = self._client().post(
            "/api/v1/email/send",
            json={
                "account_email": "test@example.com",
                "to": ["someone@example.com"],
                "subject": "Test",
                "body": "Hello",
                "unknown_field": "should_fail",
            },
        )
        assert resp.status_code == 422

    def test_mark_read_nonexistent(self):
        """PATCH /api/v1/email/messages/{uuid}/read on unknown UUID."""
        resp = self._client().patch(
            "/api/v1/email/messages/00000000-0000-0000-0000-000000000000/read",
            json={"read": True},
        )
        assert resp.status_code in (200, 404)

    def test_batch_delete_empty_list(self):
        """POST /api/v1/email/messages/batch-delete with empty list rejected."""
        resp = self._client().post(
            "/api/v1/email/messages/batch-delete",
            json={"uuids": []},
        )
        assert resp.status_code == 422  # min_length=1

    def test_import_eml_no_path(self):
        """POST /api/v1/email/import-eml without path returns 400."""
        resp = self._client().post("/api/v1/email/import-eml", json={})
        assert resp.status_code == 400
