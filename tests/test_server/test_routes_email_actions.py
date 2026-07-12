"""Tests for email action REST API routes — send, trash, batch ops."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app
from lighterbird.server.deps import get_email_service


class TestEmailActionsAPI:
    """Test /api/v1/email action endpoints."""

    def _client(self):
        return TestClient(create_app())

    def _client_with_mock_email_svc(self) -> tuple[TestClient, MagicMock]:
        """Return (client, mock_email_svc) with the email service overridden.

        The mock replaces ``get_email_service`` so route handlers receive a
        MagicMock instead of the real ``EmailService`` singleton.
        """
        app = create_app()
        mock_svc = MagicMock()
        app.dependency_overrides[get_email_service] = lambda: mock_svc
        client = TestClient(app)
        return client, mock_svc

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

    def test_send_with_signature_format_accepted(self):
        """POST /api/v1/email/send accepts signature_format field."""
        client, mock_svc = self._client_with_mock_email_svc()
        mock_svc.send_email.return_value = {"status": "sent"}
        resp = client.post(
            "/api/v1/email/send",
            json={
                "account_email": "test@example.com",
                "to": ["someone@example.com"],
                "subject": "Test",
                "body": "Hello",
                "signature_format": "html",
            },
        )
        # Should pass schema validation (actual send may fail for other reasons)
        assert resp.status_code == 201
        # Verify the mock received signature_format
        _, kwargs = mock_svc.send_email.call_args
        assert kwargs.get("signature_format") == "html"

    def test_send_with_in_reply_to_accepted(self):
        """POST /api/v1/email/send accepts in_reply_to field."""
        client, mock_svc = self._client_with_mock_email_svc()
        mock_svc.send_email.return_value = {"status": "sent"}
        resp = client.post(
            "/api/v1/email/send",
            json={
                "account_email": "test@example.com",
                "to": ["someone@example.com"],
                "subject": "Test",
                "body": "Hello",
                "in_reply_to": "<msg123@example.com>",
            },
        )
        assert resp.status_code == 201
        _, kwargs = mock_svc.send_email.call_args
        assert kwargs.get("in_reply_to") == "<msg123@example.com>"

    def test_send_with_attachments_accepted(self):
        """POST /api/v1/email/send accepts attachments field."""
        client, mock_svc = self._client_with_mock_email_svc()
        mock_svc.send_email.return_value = {"status": "sent"}
        resp = client.post(
            "/api/v1/email/send",
            json={
                "account_email": "test@example.com",
                "to": ["someone@example.com"],
                "subject": "Test",
                "body": "Hello",
                "attachments": [
                    {"name": "report.pdf", "data": "dGVzdA=="},
                    {"name": "photo.jpg", "data": "cGhvdG8="},
                ],
            },
        )
        assert resp.status_code == 201
        _, kwargs = mock_svc.send_email.call_args
        assert kwargs.get("attachments") == [
            {"name": "report.pdf", "data": "dGVzdA=="},
            {"name": "photo.jpg", "data": "cGhvdG8="},
        ]

    def test_send_with_attachments_empty_list_accepted(self):
        """POST /api/v1/email/send accepts empty attachments list."""
        client, mock_svc = self._client_with_mock_email_svc()
        mock_svc.send_email.return_value = {"status": "sent"}
        resp = client.post(
            "/api/v1/email/send",
            json={
                "account_email": "test@example.com",
                "to": ["someone@example.com"],
                "subject": "Test",
                "body": "Hello",
                "attachments": [],
            },
        )
        assert resp.status_code == 201

    def test_send_with_save_sample_default(self):
        """POST /api/v1/email/send defaults save_as_sample to True."""
        client, mock_svc = self._client_with_mock_email_svc()
        mock_svc.send_email.return_value = {"status": "sent"}
        resp = client.post(
            "/api/v1/email/send",
            json={
                "account_email": "test@example.com",
                "to": ["someone@example.com"],
                "subject": "Test",
                "body": "Hello",
            },
        )
        assert resp.status_code == 201
        _, kwargs = mock_svc.send_email.call_args
        assert kwargs.get("save_as_sample") is True

    def test_send_with_save_sample_false(self):
        """POST /api/v1/email/send accepts save_as_sample=False."""
        client, mock_svc = self._client_with_mock_email_svc()
        mock_svc.send_email.return_value = {"status": "sent"}
        resp = client.post(
            "/api/v1/email/send",
            json={
                "account_email": "test@example.com",
                "to": ["someone@example.com"],
                "subject": "Test",
                "body": "Hello",
                "save_as_sample": False,
            },
        )
        assert resp.status_code == 201
        _, kwargs = mock_svc.send_email.call_args
        assert kwargs.get("save_as_sample") is False

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
