"""Tests for email action REST API routes — send, trash, batch ops."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestEmailActionsAPI:
    """Test /api/v1/email action endpoints."""

    def _client(self):
        return TestClient(create_app())

    def _post_send(self, **overrides):
        """Helper: POST /api/v1/email/send with sensible defaults."""
        body = {
            "account_email": "test@example.com",
            "to": ["someone@example.com"],
            "subject": "Test",
            "body": "Hello",
            **overrides,
        }
        return self._client().post("/api/v1/email/send", json=body)

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
        resp = self._post_send(unknown_field="should_fail")
        assert resp.status_code == 422

    def test_send_with_signature_format_accepted_by_schema(self):
        """POST /api/v1/email/send: signature_format passes schema validation.

        Returns 422 from service ValueError (string detail), not from Pydantic
        schema validation (list detail).  Asserts detail is a string to confirm
        the request passed the Pydantic schema layer.
        """
        resp = self._post_send(signature_format="html")
        data = resp.json()
        assert isinstance(data.get("detail"), str), \
            f"Expected string detail (service error), got: {data.get('detail')!r}"

    def test_send_with_in_reply_to_accepted_by_schema(self):
        """POST /api/v1/email/send: in_reply_to passes schema validation."""
        resp = self._post_send(in_reply_to="<msg123@example.com>")
        data = resp.json()
        assert isinstance(data.get("detail"), str), \
            f"Expected string detail (service error), got: {data.get('detail')!r}"

    def test_send_value_error_returns_422(self):
        """ValueError from service returns 422 with detail message."""
        resp = self._post_send()
        assert resp.status_code == 422
        data = resp.json()
        assert "detail" in data
        assert data["detail"]

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

    def test_batch_delete_hard_large_list(self):
        """POST batch-delete-hard with 1000 UUIDs accepted (no max_length=200)."""
        uuids = [f"00000000-0000-0000-0000-{i:012d}" for i in range(1000)]
        resp = self._client().post(
            "/api/v1/email/messages/batch-delete-hard",
            json={"uuids": uuids},
        )
        # Schema passes — service returns 200 (all not-found is fine)
        assert resp.status_code == 200

    def test_batch_delete_hard_response_includes_count(self):
        """POST batch-delete-hard returns count of processed messages
        even when none exist (verifies backlog processing doesn't crash)."""
        uuids = ["00000000-0000-0000-0000-000000000001"]
        resp = self._client().post(
            "/api/v1/email/messages/batch-delete-hard",
            json={"uuids": uuids},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "status" in data
        assert "errors" in data
        # All not-found messages are reported as errors
        assert len(data["errors"]) > 0

    def test_batch_delete_hard_empty_list(self):
        """POST batch-delete-hard with empty list rejected."""
        resp = self._client().post(
            "/api/v1/email/messages/batch-delete-hard",
            json={"uuids": []},
        )
        assert resp.status_code == 422

    def test_batch_move_large_list(self):
        """POST batch-move with 1000 UUIDs accepted (no max_length=200)."""
        uuids = [f"00000000-0000-0000-0000-{i:012d}" for i in range(1000)]
        resp = self._client().post(
            "/api/v1/email/messages/batch-move",
            json={"uuids": uuids, "destination_folder": "Trash"},
        )
        assert resp.status_code == 200

    def test_batch_move_empty_list(self):
        """POST batch-move with empty list rejected."""
        resp = self._client().post(
            "/api/v1/email/messages/batch-move",
            json={"uuids": [], "destination_folder": "Trash"},
        )
        assert resp.status_code == 422

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


class TestEmailSignaturesAPI:
    """Test GET /api/v1/email/signatures endpoint."""

    def _client(self):
        from lighterbird.server.deps import reset_services
        reset_services()
        return TestClient(create_app())

    def test_signatures_empty_list(self):
        """GET /api/v1/email/signatures returns empty list when none exist."""
        resp = self._client().get("/api/v1/email/signatures")
        assert resp.status_code == 200
        data = resp.json()
        assert "signatures" in data
        assert data["signatures"] == []

    def test_signatures_with_seeded_data(self):
        """GET /api/v1/email/signatures returns seeded signatures."""
        from lighterbird.server.deps import reset_services, get_email_service
        reset_services()
        svc = get_email_service()

        # Seed a signature via the service
        svc.signatures.create(
            name="work",
            signature_text="Best regards,\nJohn",
            signature_format="plain",
        )
        svc.signatures.create(
            name="personal",
            signature_text="Cheers,\nJohn",
            signature_format="markdown",
        )

        client = TestClient(create_app())
        resp = client.get("/api/v1/email/signatures")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["signatures"]) == 2

        sigs_by_name = {s["name"]: s for s in data["signatures"]}
        assert sigs_by_name["work"]["signature_text"] == "Best regards,\nJohn"
        assert sigs_by_name["work"]["signature_format"] == "plain"
        assert sigs_by_name["personal"]["signature_format"] == "markdown"
        # No account defaults yet
        assert "default_for" not in sigs_by_name["work"]

    def test_signatures_with_account_default(self):
        """GET /api/v1/email/signatures enriches with default_for."""
        from lighterbird.server.deps import reset_services, get_email_service
        reset_services()
        svc = get_email_service()

        sig = svc.signatures.create(
            name="work",
            signature_text="Best,\nJohn",
            signature_format="plain",
        )
        # Create an account and set it as default
        svc.create_account(
            {"email": "john@work.com",
             "name": "John Work",
             "imap_server": "imap.work.com",
             "smtp_server": "smtp.work.com"},
            password="pw",
        )
        svc.signatures.set_account_default("john@work.com", sig["uuid"])

        client = TestClient(create_app())
        resp = client.get("/api/v1/email/signatures")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["signatures"]) == 1
        sig_data = data["signatures"][0]
        assert sig_data["default_for"] == ["john@work.com"]
