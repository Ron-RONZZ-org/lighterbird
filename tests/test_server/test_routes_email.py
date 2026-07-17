"""Tests for email REST API routes — messages, folders, views, advanced search params."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestEmailMessagesAPI:
    """Test /api/v1/email endpoints for messages and folders."""

    def _client(self):
        return TestClient(create_app())

    def test_list_messages_empty(self):
        """GET /api/v1/email/messages returns empty list."""
        resp = self._client().get("/api/v1/email/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert data["messages"] == []

    def test_get_message_nonexistent_returns_404(self):
        """GET /api/v1/email/messages/{uuid} with unknown UUID returns 404."""
        resp = self._client().get(
            "/api/v1/email/messages/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404

    def test_list_folders_empty(self):
        """GET /api/v1/email/folders returns empty list."""
        resp = self._client().get("/api/v1/email/folders")
        assert resp.status_code == 200
        data = resp.json()
        assert "folders" in data

    def test_list_folders_includes_decoded_name(self):
        """GET /api/v1/email/folders returns decoded_name for each folder
        (IMAP modified UTF-7 decoded for display)."""
        resp = self._client().get("/api/v1/email/folders")
        assert resp.status_code == 200
        data = resp.json()
        for f in data["folders"]:
            assert "decoded_name" in f, f"Missing decoded_name for folder {f['folder_name']!r}"
            # decoded_name is always a string (may be same as folder_name for ASCII)
            assert isinstance(f["decoded_name"], str)
            # decoded_name should never contain raw IMAP UTF-7 sequences
            assert "&-" not in f["decoded_name"] or f["decoded_name"] == "&amp;"

    def test_create_folder_no_account(self):
        """POST /api/v1/email/folders without account_email returns 422."""
        resp = self._client().post("/api/v1/email/folders?folder_name=Test")
        assert resp.status_code == 422

    def test_create_folder_unknown_account(self):
        """POST /api/v1/email/folders with nonexistent account returns 404."""
        resp = self._client().post(
            "/api/v1/email/folders?account_email=nobody@example.com&folder_name=Test",
        )
        assert resp.status_code == 404

    def test_rename_folder_no_account(self):
        """PATCH /api/v1/email/folders without account_email returns 422."""
        resp = self._client().patch(
            "/api/v1/email/folders/INBOX?new_name=INBOX2",
        )
        assert resp.status_code == 422

    def test_rename_folder_no_new_name(self):
        """PATCH /api/v1/email/folders without new_name returns 422."""
        resp = self._client().patch(
            "/api/v1/email/folders/INBOX?account_email=test@example.com",
        )
        assert resp.status_code == 422

    def test_rename_folder_unknown_account(self):
        """PATCH /api/v1/email/folders with nonexistent account returns 404."""
        resp = self._client().patch(
            "/api/v1/email/folders/INBOX"
            "?account_email=nobody@example.com&new_name=INBOX2",
        )
        assert resp.status_code == 404

    def test_delete_folder_no_account(self):
        """DELETE /api/v1/email/folders without account_email returns 422."""
        resp = self._client().delete(
            "/api/v1/email/folders/Test",
        )
        assert resp.status_code == 422

    def test_delete_folder_unknown_account(self):
        """DELETE /api/v1/email/folders with nonexistent account returns 404."""
        resp = self._client().delete(
            "/api/v1/email/folders/Test?account_email=nobody@example.com",
        )
        assert resp.status_code == 404

    def test_get_message_conversation_nonexistent(self):
        """GET /api/v1/email/messages/{uuid}/conversation returns empty."""
        resp = self._client().get(
            "/api/v1/email/messages/00000000-0000-0000-0000-000000000000/conversation"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data


class TestEmailSearchAPI:
    """Test advanced search query parameters in list_messages endpoint."""

    def _client(self):
        return TestClient(create_app())

    def test_header_param(self):
        resp = self._client().get("/api/v1/email/messages?header=true")
        assert resp.status_code == 200

    def test_body_param(self):
        resp = self._client().get("/api/v1/email/messages?body=true")
        assert resp.status_code == 200

    def test_combined_params(self):
        params = ("from=alice&to=bob&subject=report"
                  "&participant=dave&priority=1&folder=INBOX"
                  "&after=2024-01-01&before=2024-12-31")
        resp = self._client().get(f"/api/v1/email/messages?{params}")
        assert resp.status_code == 200

    def test_sender_alias(self):
        resp = self._client().get("/api/v1/email/messages?sender=alice")
        assert resp.status_code == 200

    def test_cc_bcc_params(self):
        resp = self._client().get("/api/v1/email/messages?cc=carol&bcc=bob")
        assert resp.status_code == 200
