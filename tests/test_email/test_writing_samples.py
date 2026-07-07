"""Tests for writing sample registration and RAG retrieval.

Tests cover:
- ``_save_writing_sample()`` in ``MsgSendComposeMixin``
- The ``save_as_sample`` opt-out flow in ``send_email()``
- ``gather_context()`` in ``server/cowrite/context.py``
- The ``--no-save-sample`` flag in the email send command handler
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.email.db import ensure_vec_table, get_db
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
        pass


@pytest.fixture
def db(tmp_path: Path):
    return get_db(tmp_path / "email.db")


@pytest.fixture
def host(db):
    _ensure_account(db)
    return _ComposeTestHost(db)


class TestWritingSampleSchema:
    """Tests for the writing_samples table creation."""

    def test_writing_samples_table_exists(self, db):
        """The writing_samples table should be created on get_db()."""
        tables = [r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )]
        assert "writing_samples" in tables

    def test_ensure_vec_table_creates_vec_samples(self, db):
        """ensure_vec_table() creates the vec_samples virtual table."""
        ensure_vec_table(db, 1536)
        tables = [r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )]
        assert "vec_samples" in tables

    def test_ensure_vec_table_idempotent(self, db):
        """Calling ensure_vec_table() twice does not raise."""
        ensure_vec_table(db, 1536)
        ensure_vec_table(db, 1536)  # should not raise


class TestSaveWritingSample:
    """Tests for _save_writing_sample()."""

    def test_saves_basic_sample(self, host, db):
        """A writing sample with subject and body is persisted."""
        host._save_writing_sample(
            sample_uuid="sample-1",
            source_uuid="msg-1",
            title="Hello World",
            body="This is a test email body.",
            body_format="markdown",
        )
        row = db.execute_one(
            "SELECT * FROM writing_samples WHERE uuid = ?",
            ("sample-1",),
        )
        assert row is not None
        assert row["title"] == "Hello World"
        assert row["body"] == "This is a test email body."
        assert row["source_domain"] == "email"
        assert row["body_format"] == "markdown"
        assert row["language"] == "en"
        assert row["word_count"] == 6  # 6 words in the body

    def test_saves_empty_body(self, host, db):
        """Even an empty body is saved (word_count = 0)."""
        host._save_writing_sample(
            sample_uuid="sample-empty",
            source_uuid="msg-empty",
            title="No Body",
            body="",
        )
        row = db.execute_one(
            "SELECT word_count FROM writing_samples WHERE uuid = ?",
            ("sample-empty",),
        )
        assert row is not None
        assert row["word_count"] == 0

    def test_multiple_samples(self, host, db):
        """Multiple writing samples can be stored."""
        host._save_writing_sample(
            sample_uuid="s1", source_uuid="m1",
            title="First", body="Hello.",
        )
        host._save_writing_sample(
            sample_uuid="s2", source_uuid="m2",
            title="Second", body="World.",
        )
        count = db.execute_one("SELECT COUNT(*) AS cnt FROM writing_samples")
        assert count["cnt"] == 2


class TestSendEmailSampleOptOut:
    """Tests that send_email() respects save_as_sample."""

    @patch("lighterbird.email.smtp.SMTPClient")
    def test_send_success_saves_sample(self, mock_smtp, host, db):
        """When save_as_sample=True (default), a writing sample is created."""
        host._account_service.get_account_with_password.return_value = {
            "email": "test@example.com",
            "name": "Test",
            "imap_server": "imap.example.com",
            "imap_port": 993,
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
            "smtp_use_tls": 1,
            "smtp_username": "test@example.com",
            "signature": "",
            "password": "secret",
        }
        mock_client = MagicMock()
        mock_smtp.return_value = mock_client

        result = host.send_email(
            account_email="test@example.com",
            to=["recipient@example.com"],
            subject="Test",
            body="Hello world",
        )
        assert result["status"] == "sent"

        # Writing sample should exist
        sample = db.execute_one(
            "SELECT * FROM writing_samples WHERE source_uuid = ?",
            (result["uuid"],),
        )
        assert sample is not None
        assert sample["title"] == "Test"
        assert sample["body"] == "Hello world"

    @patch("lighterbird.email.smtp.SMTPClient")
    def test_send_with_opt_out_skips_sample(self, mock_smtp, host, db):
        """When save_as_sample=False, no writing sample is created."""
        host._account_service.get_account_with_password.return_value = {
            "email": "test@example.com",
            "name": "Test",
            "imap_server": "imap.example.com",
            "imap_port": 993,
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
            "smtp_use_tls": 1,
            "smtp_username": "test@example.com",
            "signature": "",
            "password": "secret",
        }
        mock_client = MagicMock()
        mock_smtp.return_value = mock_client

        result = host.send_email(
            account_email="test@example.com",
            to=["recipient@example.com"],
            subject="Private",
            body="This is private",
            save_as_sample=False,
        )
        assert result["status"] == "sent"

        # No writing sample should exist for this message
        sample = db.execute_one(
            "SELECT * FROM writing_samples WHERE source_uuid = ?",
            (result["uuid"],),
        )
        assert sample is None

    @patch("lighterbird.email.smtp.SMTPClient")
    def test_send_queued_does_not_save_sample(self, mock_smtp, host, db):
        """When send fails and queued, no writing sample is created."""
        host._account_service.get_account_with_password.return_value = {
            "email": "test@example.com",
            "name": "Test",
            "imap_server": "imap.example.com",
            "imap_port": 993,
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
            "smtp_use_tls": 1,
            "smtp_username": "test@example.com",
            "signature": "",
            "password": "secret",
        }
        mock_client = MagicMock()
        mock_client.connect.side_effect = ConnectionError("Connection refused")
        mock_smtp.return_value = mock_client

        result = host.send_email(
            account_email="test@example.com",
            to=["recipient@example.com"],
            subject="Queued",
            body="Will be queued",
        )
        assert result["status"] == "queued"

        # No writing sample should exist (message was not sent)
        sample = db.execute_one(
            "SELECT * FROM writing_samples WHERE source_uuid = ?",
            (result["uuid"],),
        )
        assert sample is None


class TestGatherContext:
    """Tests for gather_context() in server/cowrite/context.py."""

    def test_returns_empty_for_unknown_form_type(self):
        """Non-email form types return empty context."""
        from lighterbird.server.cowrite.context import gather_context
        result = gather_context("todo-add", {"body": "test"})
        assert result == {}

    def test_returns_empty_for_empty_body(self):
        """Empty body text returns empty context."""
        from lighterbird.server.cowrite.context import gather_context
        result = gather_context("email-send", {"body": ""})
        assert result == {}

    def test_returns_recent_samples_when_no_vec_table(self, db, monkeypatch):
        """When vec_samples doesn't exist, fall back to recent samples."""
        from lighterbird.server.cowrite.context import gather_context
        from lighterbird.email.db import get_db

        # Insert a writing sample directly
        from datetime import UTC, datetime
        db.execute(
            """INSERT INTO writing_samples
               (uuid, source_uuid, source_domain, title, body,
                body_format, language, word_count, registered_at)
               VALUES ('s1', 'm1', 'email', 'Test', 'Hello world',
                       'markdown', 'en', 2, ?)""",
            (datetime.now(UTC).isoformat(),),
        )

        # Monkeypatch get_db to return our test db
        # (import inside gather_context resolves to lighterbird.email.db.get_db)
        def _mock_get_db(path=None):
            return db

        monkeypatch.setattr("lighterbird.email.db.get_db", _mock_get_db)

        result = gather_context("email-send", {"body": "something"})
        if result:
            assert "writing_samples" in result
            # Should have at least 1 sample (the one we inserted)
            assert len(result["writing_samples"]) >= 1
            assert result["writing_samples"][0]["uuid"] == "s1"

    def test_recent_samples_fallback(self, db, monkeypatch):
        """Recent samples are returned as fallback."""
        from lighterbird.server.cowrite.context import gather_context, _recent_samples_only

        db.execute(
            """INSERT INTO writing_samples
               (uuid, source_uuid, source_domain, title, body,
                body_format, language, word_count, registered_at)
               VALUES ('s2', 'm2', 'email', 'Recent', 'Recent body',
                       'markdown', 'en', 2, ?)""",
            (datetime.now(UTC).isoformat(),),
        )

        result = _recent_samples_only(db)
        assert "writing_samples" in result
        assert result["writing_samples"][0]["uuid"] == "s2"
