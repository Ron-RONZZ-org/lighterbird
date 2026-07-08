"""Tests for email/imap/sync.py — sync_account, SyncResult, _retry_pending_trash."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lighterbird.email.imap.sync import SyncResult, _retry_pending_trash, sync_account


class TestSyncResult:
    def test_init(self):
        r = SyncResult()
        assert r.total == 0
        assert r.new == 0
        assert r.errors == []

    def test_to_dict(self):
        r = SyncResult()
        r.total = 10
        r.new = 3
        r.errors = ["err1"]
        d = r.to_dict()
        assert d == {"total": 10, "new": 3, "errors": ["err1"]}


def _make_mock_client():
    """Create a mock IMAPClient with select_folder_ex configured."""
    client = MagicMock()
    client.select_folder_ex.return_value = (True, 12345, 0)  # (ok, UIDVALIDITY, MODSEQ)
    client.capabilities = MagicMock()
    client.capabilities.has_condstore = False
    return client


class TestSyncAccount:
    @patch("lighterbird.email.imap.sync.IMAPClient")
    def test_sync_all_folders(self, mock_client_class):
        mock_client = _make_mock_client()
        mock_client_class.return_value = mock_client

        mock_client.list_folders.return_value = [
            {"name": "INBOX", "delimiter": "/", "flags": [], "special_use": None},
            {"name": "Sent", "delimiter": "/", "flags": [], "special_use": None},
        ]
        mock_client.sync_folder.return_value = {"total": 5, "new": 2, "errors": []}

        mock_db = MagicMock()
        result = sync_account(
            host="imap.example.com", port=993, use_ssl=True,
            username="user@example.com", password="secret",
            account_email="user@example.com",
            db_store=mock_db,
        )
        assert result.total == 10  # 5 per folder × 2 folders
        assert result.new == 4  # 2 per folder × 2 folders
        assert result.errors == []
        assert mock_client.connect.called
        assert mock_client.disconnect.called

    @patch("lighterbird.email.imap.sync.IMAPClient")
    def test_sync_specific_folders(self, mock_client_class):
        mock_client = _make_mock_client()
        mock_client_class.return_value = mock_client
        mock_client.sync_folder.return_value = {"total": 3, "new": 1, "errors": []}

        result = sync_account(
            host="imap.example.com", port=993, use_ssl=True,
            username="user", password="pass",
            account_email="user@example.com",
            db_store=MagicMock(),
            folders=["INBOX"],
        )
        assert result.total == 3
        assert result.new == 1

    @patch("lighterbird.email.imap.sync.IMAPClient")
    def test_sync_force_flag(self, mock_client_class):
        mock_client = _make_mock_client()
        mock_client_class.return_value = mock_client
        mock_client.list_folders.return_value = [{"name": "INBOX", "delimiter": "/", "flags": [], "special_use": None}]
        mock_client.sync_folder.return_value = {"total": 2, "new": 2, "errors": []}

        mock_db = MagicMock()
        sync_account(
            host="imap.example.com", port=993, use_ssl=True,
            username="user", password="pass",
            account_email="user@example.com",
            db_store=mock_db,
            force=True,
        )
        call_kwargs = mock_client.sync_folder.call_args[1]
        assert call_kwargs.get("force") is True

    @patch("lighterbird.email.imap.sync.IMAPClient")
    def test_sync_error_recording(self, mock_client_class):
        mock_client = _make_mock_client()
        mock_client_class.return_value = mock_client
        mock_client.list_folders.return_value = [{"name": "INBOX", "delimiter": "/", "flags": [], "special_use": None}]
        mock_client.sync_folder.return_value = {"total": 10, "new": 0, "errors": ["Connection lost"]}

        result = sync_account(
            host="imap.example.com", port=993, use_ssl=True,
            username="user", password="pass",
            account_email="user@example.com",
            db_store=MagicMock(),
        )
        assert "Connection lost" in result.errors

    @patch("lighterbird.email.imap.sync.IMAPClient")
    def test_sync_disconnect_on_error(self, mock_client_class):
        mock_client = _make_mock_client()
        mock_client_class.return_value = mock_client
        mock_client.connect.side_effect = RuntimeError("IMAP down")

        with pytest.raises(RuntimeError):
            sync_account(
                host="imap.example.com", port=993, use_ssl=True,
                username="user", password="pass",
                account_email="user@example.com",
                db_store=MagicMock(),
            )
        # Disconnect should be called in finally block
        mock_client.disconnect.assert_called_once()

    @patch("lighterbird.email.imap.sync.IMAPClient")
    def test_sync_list_folders_failure_returns_partial_result(self, mock_client_class):
        """When list_folders() raises, sync_account should return a result
        with the error recorded, not crash."""
        mock_client = _make_mock_client()
        mock_client_class.return_value = mock_client
        mock_client.list_folders.side_effect = ConnectionError("IMAP connection lost")

        result = sync_account(
            host="imap.example.com", port=993, use_ssl=True,
            username="user", password="pass",
            account_email="user@example.com",
            db_store=MagicMock(),
        )
        # Should return a SyncResult with an error, not crash
        assert len(result.errors) >= 1
        assert any("IMAP" in e for e in result.errors)
        assert result.total == 0

    @patch("lighterbird.email.imap.sync._check_uidvalidity")
    @patch("lighterbird.email.imap.sync.IMAPClient")
    def test_sync_uidvalidity_failure_does_not_abort_loop(
        self, mock_client_class, mock_check_uv,
    ):
        """If _check_uidvalidity raises for one folder, the loop continues
        to process remaining folders."""
        mock_client = _make_mock_client()
        mock_client_class.return_value = mock_client

        mock_client.list_folders.return_value = [
            {"name": "INBOX", "delimiter": "/", "flags": [], "special_use": None},
            {"name": "Sent", "delimiter": "/", "flags": [], "special_use": None},
            {"name": "Custom", "delimiter": "/", "flags": [], "special_use": None},
        ]
        mock_client.sync_folder.return_value = {"total": 1, "new": 1, "errors": []}

        # Make _check_uidvalidity raise for the second folder (Sent)
        def raise_on_sent(db, email, folder, uv):
            if folder == "Sent":
                raise RuntimeError("UIDVALIDITY check failed")
        mock_check_uv.side_effect = raise_on_sent

        mock_db = MagicMock()
        result = sync_account(
            host="imap.example.com", port=993, use_ssl=True,
            username="user", password="pass",
            account_email="user@example.com",
            db_store=mock_db,
        )
        # All 3 folders should have been synced (errors for uidvalidity don't stop loop)
        assert result.total == 3  # 1 per folder × 3 folders
        # The second folder had a _check_uidvalidity error, but it was caught,
        # so sync_folder was still called for Sent
        assert mock_client.sync_folder.call_count == 3


class TestRetryPendingTrash:
    def test_no_pending(self):
        client = MagicMock()
        mock_db = MagicMock()
        mock_db.db.execute.return_value = []
        _retry_pending_trash(client, mock_db, "user@example.com")
        client.move_message.assert_not_called()

    def test_pending_trash_moved(self):
        client = MagicMock()
        client.move_message.return_value = True
        mock_db = MagicMock()
        mock_db.db.execute.return_value = [
            {"uuid": "uuid-1", "imap_uid": 42, "folder_name": "INBOX"},
        ]
        _retry_pending_trash(client, mock_db, "user@example.com")
        client.move_message.assert_called_once_with(42, "INBOX", "Trash")

    def test_pending_trash_move_fails_silently(self):
        client = MagicMock()
        client.move_message.side_effect = Exception("IMAP error")
        mock_db = MagicMock()
        mock_db.db.execute.return_value = [
            {"uuid": "uuid-1", "imap_uid": 42, "folder_name": "INBOX"},
        ]
        # Should not raise
        _retry_pending_trash(client, mock_db, "user@example.com")

    def test_skips_null_uid(self):
        client = MagicMock()
        mock_db = MagicMock()
        mock_db.db.execute.return_value = [
            {"uuid": "uuid-1", "imap_uid": None, "folder_name": "INBOX"},
        ]
        _retry_pending_trash(client, mock_db, "user@example.com")
        client.move_message.assert_not_called()
