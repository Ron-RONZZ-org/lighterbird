"""Tests for email/services/msg_compose.py — MsgSendComposeMixin.

The mixin needs a host class with ``self.db`` and ``self._account_service``.
We create a minimal test host for this purpose.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.email.db import get_db
from lighterbird.email.services.msg_compose import MsgSendComposeMixin

_NOW = datetime.now(UTC).isoformat()


def _ensure_account(db, email: str = "test@example.com"):
    """Insert a minimal account record + default folders for FK constraints."""
    db.execute(
        """INSERT OR IGNORE INTO accounts
           (email, name, sort_order, imap_server, imap_port, imap_use_ssl,
            smtp_server, smtp_port, smtp_use_tls, created_at, updated_at)
           VALUES (?, ?, 0, 'imap.example.com', 993, 1,
                   'smtp.example.com', 587, 1, ?, ?)""",
        (email, email.split("@")[0], _NOW, _NOW),
    )
    for folder_name in ("INBOX", "Sent", "Outbox", "Trash", "Drafts"):
        db.execute(
            "INSERT OR IGNORE INTO folders (account_email, name, created_at, updated_at)"
            " VALUES (?, ?, ?, ?)",
            (email, folder_name, _NOW, _NOW),
        )


class _ComposeTestHost(MsgSendComposeMixin):
    """Minimal host class that composes MsgSendComposeMixin with a DB."""

    def __init__(self, db):
        self.db = db
        self._account_service = MagicMock()

    def _enqueue_send(self, msg_uuid, account_email, body_format, signature,
                      priority, send_error):
        """Stub: the real implementation lives in another mixin."""
        pass


@pytest.fixture
def db(tmp_path: Path):
    return get_db(tmp_path / "email.db")


@pytest.fixture
def host(db):
    _ensure_account(db)
    return _ComposeTestHost(db)


def _mock_account(account_email="test@example.com", has_password=True, **overrides):
    """Create a fake account dict as returned by get_account_with_password."""
    acct = {
        "email": account_email,
        "name": "Test",
        "imap_server": "imap.example.com",
        "imap_port": 993,
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "smtp_use_tls": 1,
        "smtp_username": account_email,
        "signature": "",
    }
    if has_password:
        acct["password"] = "secret"
    acct.update(overrides)
    return acct


class TestSendEmail:
    """Tests for send_email() — core compose-and-send flow."""

    def test_account_not_found_raises(self, host, db):
        """When no account exists, should raise ValueError with helpful message."""
        host._account_service.get_account_with_password.return_value = None
        host._account_service.get.return_value = None
        with pytest.raises(ValueError, match="Account.*not found"):
            host.send_email(
                account_email="missing@example.com",
                to=["recipient@example.com"],
                subject="Test",
                body="Hello",
            )

    def test_account_no_password_raises(self, host, db):
        """When account has no password, should raise with actionable message."""
        host._account_service.get_account_with_password.return_value = None
        host._account_service.get.return_value = {"email": "test@example.com"}
        with pytest.raises(ValueError, match="No password configured"):
            host.send_email(
                account_email="test@example.com",
                to=["recipient@example.com"],
                subject="Test",
            )

    @patch("lighterbird.email.smtp.SMTPClient")
    def test_send_success_moves_to_sent(self, mock_smtp, host, db):
        """On successful SMTP send, message is moved from Outbox to Sent."""
        host._account_service.get_account_with_password.return_value = _mock_account()
        mock_client = MagicMock()
        mock_smtp.return_value = mock_client

        result = host.send_email(
            account_email="test@example.com",
            to=["recipient@example.com"],
            subject="Hello",
            body="World",
        )

        assert result["status"] == "sent"
        # Message should have been moved to Sent folder
        msg = host.db.execute_one(
            "SELECT folder_name FROM messages WHERE uuid = ?", (result["uuid"],)
        )
        assert msg["folder_name"] == "Sent"
        mock_client.connect.assert_called_once()
        mock_client.send_email.assert_called_once()
        mock_client.disconnect.assert_called_once()

    @patch("lighterbird.email.smtp.SMTPClient")
    def test_send_connection_failure_queues(self, mock_smtp, host, db):
        """On SMTP connection failure, message stays in Outbox for retry."""
        host._account_service.get_account_with_password.return_value = _mock_account()
        mock_client = MagicMock()
        mock_client.connect.side_effect = ConnectionError("Connection refused")
        mock_smtp.return_value = mock_client

        result = host.send_email(
            account_email="test@example.com",
            to=["recipient@example.com"],
            subject="Hello",
            body="World",
        )

        assert result["status"] == "queued"
        assert "error" in result
        # Message should still be in Outbox
        msg = host.db.execute_one(
            "SELECT folder_name FROM messages WHERE uuid = ?", (result["uuid"],)
        )
        assert msg["folder_name"] == "Outbox"

    @patch("lighterbird.email.smtp.SMTPClient")
    def test_send_with_cc_bcc(self, mock_smtp, host, db):
        """CC and BCC recipients are passed through."""
        host._account_service.get_account_with_password.return_value = _mock_account()
        mock_client = MagicMock()
        mock_smtp.return_value = mock_client

        result = host.send_email(
            account_email="test@example.com",
            to=["primary@example.com"],
            subject="CC Test",
            body="Body",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
        )

        assert result["status"] == "sent"
        call_kwargs = mock_client.send_email.call_args.kwargs
        assert "cc@example.com" in call_kwargs.get("cc", [])

    @patch("lighterbird.email.smtp.SMTPClient")
    def test_send_with_signature(self, mock_smtp, host, db):
        """Custom signature is passed to SMTPClient."""
        acct = _mock_account()
        acct["signature"] = "-- \nDefault Sig"
        host._account_service.get_account_with_password.return_value = acct
        mock_client = MagicMock()
        mock_smtp.return_value = mock_client

        result = host.send_email(
            account_email="test@example.com",
            to=["recipient@example.com"],
            subject="Sig Test",
            body="Body",
            signature="-- \nCustom Sig",
        )

        assert result["status"] == "sent"
        call_kwargs = mock_client.send_email.call_args.kwargs
        assert call_kwargs.get("signature") == "-- \nCustom Sig"

    @patch("lighterbird.email.smtp.SMTPClient")
    def test_send_uses_account_signature(self, mock_smtp, host, db):
        """When no signature override, use account's stored signature."""
        # Insert a global signature and set it as default for the account
        import uuid as _uuid
        sig_uuid = str(_uuid.uuid4())
        db.execute(
            "INSERT OR IGNORE INTO email_signatures "
            "(uuid, name, signature_text, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (sig_uuid, "default",
             "-- \nAccount Sig", _NOW, _NOW),
        )
        # Set as default for the test account
        db.execute(
            "UPDATE accounts SET default_signature_uuid = ? WHERE email = ?",
            (sig_uuid, "test@example.com"),
        )
        acct = _mock_account()
        host._account_service.get_account_with_password.return_value = acct
        mock_client = MagicMock()
        mock_smtp.return_value = mock_client

        result = host.send_email(
            account_email="test@example.com",
            to=["recipient@example.com"],
            subject="Default Sig",
            body="Body",
        )

        assert result["status"] == "sent"
        call_kwargs = mock_client.send_email.call_args.kwargs
        assert call_kwargs.get("signature") == "-- \nAccount Sig"

    def test_ensure_folder_creates(self, host, db):
        """_ensure_folder creates a folder record for the account."""
        host._ensure_folder("test@example.com", "Custom")
        row = host.db.execute_one(
            "SELECT name FROM folders WHERE account_email = ? AND name = ?",
            ("test@example.com", "Custom"),
        )
        assert row is not None
        assert row["name"] == "Custom"

    def test_ensure_folder_idempotent(self, host, db):
        host._ensure_folder("test@example.com", "Dupe")
        host._ensure_folder("test@example.com", "Dupe")  # should not raise


class TestSendEmailBodyFormats:
    """Tests for different body_format values."""

    @patch("lighterbird.email.smtp.SMTPClient")
    def test_body_format_markdown(self, mock_smtp, host, db):
        host._account_service.get_account_with_password.return_value = _mock_account()
        mock_client = MagicMock()
        mock_smtp.return_value = mock_client

        host.send_email(
            account_email="test@example.com",
            to=["r@example.com"],
            subject="MD Test",
            body="**bold**",
            body_format="markdown",
        )
        call_kwargs = mock_client.send_email.call_args.kwargs
        # body should be the original markdown, html_body the rendered HTML
        assert "**bold**" in call_kwargs.get("body", "")

    @patch("lighterbird.email.smtp.SMTPClient")
    def test_body_format_html(self, mock_smtp, host, db):
        host._account_service.get_account_with_password.return_value = _mock_account()
        mock_client = MagicMock()
        mock_smtp.return_value = mock_client

        host.send_email(
            account_email="test@example.com",
            to=["r@example.com"],
            subject="HTML Test",
            body="<p>Hello</p>",
            body_format="html",
        )
        call_kwargs = mock_client.send_email.call_args.kwargs
        assert call_kwargs.get("html_body") == "<p>Hello</p>"


class TestSaveOutboxMessage:
    """Tests for _save_outbox_message()."""

    def test_saves_message(self, host, db):
        host._save_outbox_message(
            msg_uuid="test-uuid",
            account_email="test@example.com",
            sender_email="test@example.com",
            to=["r@example.com"],
            cc=[],
            subject="Test",
            body="Body",
            body_format="plain",
            message_id="<mid@example.com>",
            in_reply_to=None,
            attachments=[],
        )
        msg = host.db.execute_one(
            "SELECT * FROM messages WHERE uuid = ?", ("test-uuid",)
        )
        assert msg is not None
        assert msg["folder_name"] == "Outbox"
        assert msg["subject"] == "Test"

    def test_saves_with_attachments(self, host, db):
        host._save_outbox_message(
            msg_uuid="att-uuid",
            account_email="test@example.com",
            sender_email="test@example.com",
            to=["r@example.com"],
            cc=[],
            subject="With Attachments",
            body="Body",
            body_format="plain",
            message_id="<mid@example.com>",
            in_reply_to=None,
            attachments=[{"name": "file.txt", "data": "aGVsbG8="}],
        )
        # Should not raise, attachment should be stored
        rows = list(host.db.execute(
            "SELECT filename FROM email_attachments WHERE message_uuid = ?",
            ("att-uuid",),
        ))
        assert len(rows) >= 1

    def test_saves_with_in_reply_to(self, host, db):
        host._save_outbox_message(
            msg_uuid="reply-uuid",
            account_email="test@example.com",
            sender_email="test@example.com",
            to=["r@example.com"],
            cc=[],
            subject="Re: Test",
            body="Body",
            body_format="plain",
            message_id="<mid@example.com>",
            in_reply_to="<parent@example.com>",
            attachments=[],
        )
        msg = host.db.execute_one(
            "SELECT in_reply_to FROM messages WHERE uuid = ?", ("reply-uuid",)
        )
        assert msg["in_reply_to"] == "<parent@example.com>"


class TestReconstructAttachments:
    def test_no_attachments(self, host, db):
        result = host._reconstruct_attachments("nonexistent-uuid")
        assert result == []

    def test_with_attachment(self, host, db):
        """Reconstruct an attachment that was stored."""
        att_uuid = "att-test-uuid"
        host._save_outbox_message(
            msg_uuid=att_uuid,
            account_email="test@example.com",
            sender_email="test@example.com",
            to=["r@example.com"],
            cc=[],
            subject="With Att",
            body="Body",
            body_format="plain",
            message_id="<mid@test>",
            in_reply_to=None,
            attachments=[{"name": "file.txt", "data": "aGVsbG8="}],
        )
        result = host._reconstruct_attachments(att_uuid)
        assert len(result) >= 1
        assert result[0]["name"] == "file.txt"
        assert result[0]["data"] == "aGVsbG8="
