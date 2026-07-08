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


class TestEmailPreviewAPI:
    """Test POST /api/v1/email/preview endpoint."""

    def _client(self):
        return TestClient(create_app())

    def test_preview_basic(self):
        """POST /api/v1/email/preview returns HTML with subject and body."""
        resp = self._client().post("/api/v1/email/preview", json={
            "subject": "Hello",
            "body": "World",
            "body_format": "plain",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "html" in data
        assert "Hello" in data["html"]
        assert "World" in data["html"]

    def test_preview_with_sig(self):
        """Preview with signature includes signature text."""
        resp = self._client().post("/api/v1/email/preview", json={
            "subject": "Test",
            "body": "Body text",
            "body_format": "markdown",
            "signature_text": "-- John",
            "signature_format": "plain",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "John" in data["html"]

    def test_preview_markdown_conversion(self):
        """Markdown body is converted to HTML in preview."""
        resp = self._client().post("/api/v1/email/preview", json={
            "subject": "Test",
            "body": "**bold** and *italic*",
            "body_format": "markdown",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "<strong>" in data["html"]
        assert "<em>" in data["html"]

    def test_preview_html_passthrough(self):
        """HTML body is passed through as-is."""
        resp = self._client().post("/api/v1/email/preview", json={
            "subject": "Test",
            "body": "<p>Paragraph</p>",
            "body_format": "html",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "<p>Paragraph</p>" in data["html"]

    def test_preview_empty_body(self):
        """Empty body returns HTML with just subject."""
        resp = self._client().post("/api/v1/email/preview", json={
            "subject": "Just Subject",
            "body": "",
            "body_format": "markdown",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "Just Subject" in data["html"]

    def test_preview_extra_fields_rejected(self):
        """Unknown fields return 422."""
        resp = self._client().post("/api/v1/email/preview", json={
            "subject": "Test",
            "body": "Body",
            "body_format": "plain",
            "unknown": "rejected",
        })
        assert resp.status_code == 422

    def test_preview_with_empty_signature(self):
        """signature_text=None does not crash."""
        resp = self._client().post("/api/v1/email/preview", json={
            "subject": "Test",
            "body": "Body",
            "body_format": "plain",
            "signature_text": None,
        })
        assert resp.status_code == 200
