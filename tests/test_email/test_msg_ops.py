"""Tests for email/services/msg_ops.py — MessageOpsService."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from lighterbird.email.services.msg_ops import MessageOpsService

# IMAPClient and SMTPClient are imported inside function bodies in msg_ops.py.
# We patch them at their source module, not in msg_ops' namespace.
IMAP_PATCH = "lighterbird.email.imap.client.IMAPClient"
SMTP_PATCH = "lighterbird.email.smtp.SMTPClient"

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute.return_value = None
    db.execute_one.return_value = None
    return db


@pytest.fixture
def mock_account_service():
    svc = MagicMock()
    svc.get_account_with_password.return_value = {
        "email": "user@example.com",
        "imap_server": "imap.example.com",
        "imap_port": 993,
        "imap_use_ssl": 1,
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "smtp_use_tls": 1,
        "password": "secret",
        "signature": "",
    }
    svc.get.return_value = {"email": "user@example.com"}
    return svc


@pytest.fixture
def msg_ops(mock_db, mock_account_service):
    return MessageOpsService(mock_db, mock_account_service)


# ── mark_read ────────────────────────────────────────────────────────────────


class TestMarkRead:
    def test_mark_read(self, msg_ops, mock_db):
        msg_ops.db.execute_one.return_value = {
            "uuid": "msg-1", "account_email": "user@example.com",
            "imap_uid": 42, "folder_name": "INBOX",
            "is_read": 0, "is_deleted": 0,
        }
        msg_ops.mark_read("msg-1", is_read=True)
        # Should update local DB
        assert mock_db.execute.call_count >= 1

    def test_mark_unread(self, msg_ops, mock_db):
        msg_ops.db.execute_one.return_value = {
            "uuid": "msg-1", "account_email": "user@example.com",
            "imap_uid": 42, "folder_name": "INBOX",
            "is_read": 1, "is_deleted": 0,
        }
        msg_ops.mark_read("msg-1", is_read=False)
        assert mock_db.execute.call_count >= 1


# ── _imap_sync_flags ─────────────────────────────────────────────────────────


class TestImapSyncFlags:
    def test_no_message_returns(self, msg_ops):
        msg_ops.db.execute_one.return_value = None
        msg_ops._imap_sync_flags("nonexistent")
        # No IMAP attempt should be made

    def test_no_account_email_returns(self, msg_ops):
        msg_ops.db.execute_one.return_value = {
            "uuid": "msg-1", "account_email": "", "imap_uid": 42,
            "folder_name": "INBOX", "is_read": 0, "is_deleted": 0,
        }
        msg_ops._imap_sync_flags("msg-1")

    def test_no_imap_uid_returns(self, msg_ops):
        msg_ops.db.execute_one.return_value = {
            "uuid": "msg-1", "account_email": "user@example.com",
            "imap_uid": None, "folder_name": "INBOX",
            "is_read": 0, "is_deleted": 0,
        }
        msg_ops._imap_sync_flags("msg-1")

    @patch(IMAP_PATCH)
    def test_imap_sync_flags_success(self, mock_client_class, msg_ops):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.set_flags.return_value = True

        msg_ops.db.execute_one.return_value = {
            "uuid": "msg-1", "account_email": "user@example.com",
            "imap_uid": 42, "folder_name": "INBOX",
            "is_read": 1, "is_deleted": 0,
        }

        msg_ops._imap_sync_flags("msg-1")
        mock_client.connect.assert_called_once()
        mock_client.set_flags.assert_called_once()
        mock_client.disconnect.assert_called_once()

    @patch(IMAP_PATCH)
    def test_imap_sync_flags_enqueues_on_failure(self, mock_client_class, msg_ops):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.set_flags.side_effect = RuntimeError("IMAP down")

        msg_ops.db.execute_one.return_value = {
            "uuid": "msg-1", "account_email": "user@example.com",
            "imap_uid": 42, "folder_name": "INBOX",
            "is_read": 0, "is_deleted": 1,
        }

        msg_ops._imap_sync_flags("msg-1")
        # Should have enqueued sync (one execute call in _enqueue_sync)
        assert msg_ops.db.execute.call_count >= 1
        mock_client.disconnect.assert_called_once()

    @patch(IMAP_PATCH)
    def test_imap_sync_flags_no_password_enqueues(self, mock_client_class, msg_ops, mock_account_service):
        mock_account_service.get_account_with_password.return_value = None
        msg_ops.db.execute_one.return_value = {
            "uuid": "msg-1", "account_email": "user@example.com",
            "imap_uid": 42, "folder_name": "INBOX",
            "is_read": 0, "is_deleted": 0,
        }
        msg_ops._imap_sync_flags("msg-1")
        # Should enqueue (call execute at least once)
        assert msg_ops.db.execute.called


# ── _enqueue_sync ────────────────────────────────────────────────────────────


class TestEnqueueSync:
    def test_enqueue_sync_inserts(self, msg_ops):
        msg_ops._enqueue_sync({
            "uuid": "msg-1", "account_email": "user@example.com",
            "folder_name": "INBOX", "imap_uid": 42,
            "is_read": 0, "is_deleted": 0,
        })
        msg_ops.db.execute.assert_called_once()


# ── process_sync_backlog ─────────────────────────────────────────────────────


class TestProcessSyncBacklog:
    def test_no_entries(self, msg_ops):
        msg_ops.db.execute.return_value = []
        assert msg_ops.process_sync_backlog() == 0

    def test_stale_null_uid_entries_cleaned(self, msg_ops):
        msg_ops.db.execute.return_value = [
            {"id": 1, "imap_uid": None, "account_email": "user@example.com",
             "msg_uuid": "m1", "folder_name": "INBOX",
             "is_read": 0, "is_deleted": 0, "created_at": "now"},
        ]
        count = msg_ops.process_sync_backlog()
        assert count == 0
        # Should have deleted the stale entry
        delete_calls = [c for c in msg_ops.db.execute.call_args_list if "DELETE" in str(c)]
        assert len(delete_calls) >= 1

    @patch(IMAP_PATCH)
    def test_process_sync_backlog_success(self, mock_client_class, msg_ops):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.set_flags.return_value = True

        msg_ops.db.execute.return_value = [
            {"id": 1, "imap_uid": 42, "account_email": "user@example.com",
             "msg_uuid": "m1", "folder_name": "INBOX",
             "is_read": 1, "is_deleted": 0, "created_at": "now"},
        ]

        count = msg_ops.process_sync_backlog()
        assert count == 1

    @patch(IMAP_PATCH)
    def test_process_sync_backlog_failure_retries(self, mock_client_class, msg_ops):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.set_flags.side_effect = RuntimeError("IMAP error")

        msg_ops.db.execute.return_value = [
            {"id": 1, "imap_uid": 42, "account_email": "user@example.com",
             "msg_uuid": "m1", "folder_name": "INBOX",
             "is_read": 1, "is_deleted": 0, "created_at": "now"},
        ]

        count = msg_ops.process_sync_backlog()
        assert count == 0
        # Should have updated retries
        update_calls = [c for c in msg_ops.db.execute.call_args_list if "UPDATE" in str(c)]
        assert len(update_calls) >= 1


# ── trash_message ────────────────────────────────────────────────────────────


class TestTrashMessage:
    def test_trash_nonexistent_message(self, msg_ops):
        msg_ops.db.execute_one.return_value = None
        msg_ops.trash_message("nonexistent")
        # Should not raise

    @patch(IMAP_PATCH)
    def test_trash_message_with_imap_success(self, mock_client_class, msg_ops):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.move_message.return_value = True

        msg_ops.db.execute_one.return_value = {
            "uuid": "msg-1", "account_email": "user@example.com",
            "imap_uid": 42, "folder_name": "INBOX",
            "is_read": 0, "is_deleted": 0,
        }

        msg_ops.trash_message("msg-1")
        # Should have moved to Trash and updated DB
        mock_client.move_message.assert_called_once_with(42, "INBOX", "Trash")
        mock_client.disconnect.assert_called_once()

    def test_trash_message_no_imap_uid(self, msg_ops):
        msg_ops.db.execute_one.return_value = {
            "uuid": "msg-1", "account_email": "user@example.com",
            "imap_uid": None, "folder_name": "INBOX",
            "is_read": 0, "is_deleted": 0,
        }
        msg_ops.trash_message("msg-1")


# ── batch_trash_messages ─────────────────────────────────────────────────────


class TestBatchTrashMessages:
    def test_batch_trash_empty(self, msg_ops):
        result = msg_ops.batch_trash_messages([])
        assert result == {"count": 0, "queued": 0}

    def test_batch_trash_one(self, msg_ops):
        msg_ops.db.execute_one.return_value = {
            "uuid": "msg-1", "account_email": "user@example.com",
            "imap_uid": 42, "folder_name": "INBOX",
            "is_read": 0, "is_deleted": 0,
        }
        result = msg_ops.batch_trash_messages(["msg-1"])
        assert result["count"] == 1
        assert result["queued"] == 1

    def test_batch_trash_skips_already_deleted(self, msg_ops):
        msg_ops.db.execute_one.return_value = None  # already deleted
        result = msg_ops.batch_trash_messages(["msg-1"])
        assert result["count"] == 0
        assert result["queued"] == 0


# ── send_email (high-level) ──────────────────────────────────────────────────


class TestSendEmail:
    @patch(SMTP_PATCH)
    def test_send_email_success(self, mock_smtp_class, msg_ops, mock_account_service):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        result = msg_ops.send_email(
            account_email="user@example.com",
            to=["recipient@example.com"],
            subject="Test",
            body="Hello",
        )
        assert result["status"] == "sent"
        assert result["uuid"] is not None
        mock_smtp.connect.assert_called_once()
        mock_smtp.send_email.assert_called_once()
        mock_smtp.disconnect.assert_called_once()

    @patch(SMTP_PATCH)
    def test_send_email_queued_on_failure(self, mock_smtp_class, msg_ops):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp
        mock_smtp.connect.side_effect = ConnectionError("SMTP unavailable")

        result = msg_ops.send_email(
            account_email="user@example.com",
            to=["recipient@example.com"],
            subject="Test",
            body="Hello",
        )
        assert result["status"] == "queued"
        assert "error" in result

    @patch(SMTP_PATCH)
    def test_send_email_markdown_body(self, mock_smtp_class, msg_ops):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        result = msg_ops.send_email(
            account_email="user@example.com",
            to=["to@example.com"],
            subject="MD Test",
            body="**bold** text",
            body_format="markdown",
        )
        assert result["status"] == "sent"

    def test_send_email_no_account(self, msg_ops, mock_account_service):
        mock_account_service.get_account_with_password.return_value = None
        mock_account_service.get.return_value = None
        with pytest.raises(ValueError, match="not found"):
            msg_ops.send_email(
                account_email="nonexistent@test.com",
                to=["to@example.com"],
                subject="Test",
                body="Hello",
            )

    def test_send_email_no_password(self, msg_ops, mock_account_service):
        mock_account_service.get_account_with_password.return_value = None
        mock_account_service.get.return_value = {"email": "user@example.com"}
        with pytest.raises(ValueError, match="No password configured"):
            msg_ops.send_email(
                account_email="user@example.com",
                to=["to@example.com"],
                subject="Test",
                body="Hello",
            )


# ── process_send_queue ───────────────────────────────────────────────────────


class TestProcessSendQueue:
    def test_no_entries(self, msg_ops):
        msg_ops.db.execute.return_value = []
        result = msg_ops.process_send_queue()
        assert result == {"sent": 0, "retrying": 0, "failed": 0, "errors": []}

    def _setup_send_queue_mocks(self, msg_ops, queue_entry):
        """Configure db.execute to return queue entry first, then empty attachments."""
        # process_send_queue makes many db.execute calls:
        # 1. fetch queue entries → list with entry
        # 2. _reconstruct_attachments (attachment query) → empty list
        # 3. mark as 'running'
        # 4. mark_sent (UPDATE) or update retries
        # 5. mark_sent (DELETE)
        # Use a function side_effect to handle unlimited calls
        call_log = {"count": 0}
        def execute_side_effect(*args, **kwargs):
            call_log["count"] += 1
            sql = args[0] if args else ""
            # First call: fetch queue entries
            if call_log["count"] == 1:
                return [queue_entry]
            # Attachment query
            if "email_attachments" in sql:
                return []
            # All other calls succeed silently
            return None
        msg_ops.db.execute.side_effect = execute_side_effect

    @patch(SMTP_PATCH)
    def test_process_send_queue_success(self, mock_smtp_class, msg_ops):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        self._setup_send_queue_mocks(msg_ops, {
            "msg_uuid": "msg-1", "account_email": "user@example.com",
            "body_format": "plain", "signature": "", "priority": 3,
            "retries": 0, "max_retries": 10,
            "to_recipients": '["to@example.com"]',
            "cc_recipients": "[]",
            "subject": "Test", "body": "Hello",
            "from_addr": "user@example.com",
        })

        result = msg_ops.process_send_queue()
        assert result["sent"] == 1

    @patch(SMTP_PATCH)
    def test_process_send_queue_retries_on_failure(self, mock_smtp_class, msg_ops):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp
        mock_smtp.connect.side_effect = ConnectionError("SMTP down")

        self._setup_send_queue_mocks(msg_ops, {
            "msg_uuid": "msg-1", "account_email": "user@example.com",
            "body_format": "plain", "signature": "", "priority": 3,
            "retries": 0, "max_retries": 10,
            "to_recipients": '["to@example.com"]',
            "cc_recipients": "[]",
            "subject": "Test", "body": "Hello",
            "from_addr": "user@example.com",
        })

        result = msg_ops.process_send_queue()
        assert result["retrying"] == 1

    @patch(SMTP_PATCH)
    def test_process_send_queue_exhausted_retries(self, mock_smtp_class, msg_ops):
        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp
        mock_smtp.connect.side_effect = ConnectionError("SMTP down")

        self._setup_send_queue_mocks(msg_ops, {
            "msg_uuid": "msg-1", "account_email": "user@example.com",
            "body_format": "plain", "signature": "", "priority": 3,
            "retries": 9, "max_retries": 10,
            "to_recipients": '["to@example.com"]',
            "cc_recipients": "[]",
            "subject": "Test", "body": "Hello",
            "from_addr": "user@example.com",
        })

        result = msg_ops.process_send_queue()
        assert result["failed"] == 1


# ── process_trash_backlog ────────────────────────────────────────────────────


class TestProcessTrashBacklog:
    def test_no_entries(self, msg_ops):
        msg_ops.db.execute.return_value = []
        assert msg_ops.process_trash_backlog() == 0

    @patch(IMAP_PATCH)
    def test_process_trash_backlog_success(self, mock_client_class, msg_ops):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.move_message.return_value = True

        msg_ops.db.execute.return_value = [
            {"id": 1, "imap_uid": 42, "account_email": "user@example.com",
             "msg_uuid": "m1", "folder_name": "INBOX",
             "is_read": 1, "is_deleted": 1, "created_at": "now"},
        ]

        count = msg_ops.process_trash_backlog()
        assert count == 1

    @patch(IMAP_PATCH)
    def test_process_trash_backlog_move_failure(self, mock_client_class, msg_ops):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.move_message.return_value = False

        msg_ops.db.execute.return_value = [
            {"id": 1, "imap_uid": 42, "account_email": "user@example.com",
             "msg_uuid": "m1", "folder_name": "INBOX",
             "is_read": 1, "is_deleted": 1, "created_at": "now"},
        ]

        count = msg_ops.process_trash_backlog()
        assert count == 0


# ── move_message ─────────────────────────────────────────────────────────────


class TestMoveMessage:
    def test_move_message(self, msg_ops):
        msg_ops.move_message("msg-1", "Archive")
        msg_ops.db.execute.assert_called_once()
        call_args = msg_ops.db.execute.call_args[0]
        assert "UPDATE messages" in call_args[0]
        assert "folder_name" in call_args[0]
