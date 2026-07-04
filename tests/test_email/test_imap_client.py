"""Tests for email/imap/client.py — IMAPClient, _parse_list_response, store_message."""
from __future__ import annotations

import email as email_lib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from lighterbird.email.imap.client import (
    IMAPClient,
    _parse_list_response,
    store_message,
    _insert_message,
)


# ── _parse_list_response ─────────────────────────────────────────────────────


class TestParseListResponse:
    def test_parse_inbox(self):
        # Real IMAP LIST response: (flags) "/" name (name unquoted for simple names)
        line = b'(\\HasNoChildren) "/" INBOX'
        result = _parse_list_response(line)
        assert result is not None
        assert result["name"] == "INBOX"
        assert result["delimiter"] == "/"
        assert result["flags"] == ["\\HasNoChildren"]

    def test_parse_with_special_use(self):
        line = b'(\\HasNoChildren \\Sent) "/" Sent'
        result = _parse_list_response(line)
        assert result is not None
        assert result["special_use"] == "Sent"

    def test_parse_trash_special_use(self):
        line = b'(\\Trash) "/" Trash'
        result = _parse_list_response(line)
        assert result is not None
        assert result["special_use"] == "Trash"

    def test_parse_junk(self):
        line = b'(\\Junk) "/" Spam'
        result = _parse_list_response(line)
        assert result is not None
        assert result["special_use"] == "Junk"

    def test_parse_empty_line(self):
        assert _parse_list_response(b"") is None

    def test_parse_no_name(self):
        line = b'(\\NoSelect) "/""'
        result = _parse_list_response(line)
        assert result is None

    def test_parse_multiple_flags(self):
        line = b'(\\HasNoChildren \\Unmarked) "/" INBOX'
        result = _parse_list_response(line)
        assert result is not None
        assert "\\HasNoChildren" in result["flags"]
        assert "\\Unmarked" in result["flags"]

    def test_parse_different_delimiter(self):
        line = b'(\\HasNoChildren) "." INBOX'
        result = _parse_list_response(line)
        assert result is not None
        assert result["delimiter"] == "."

    def test_parse_nested_name(self):
        """Names with spaces are quoted in IMAP responses."""
        line = b'(\\HasChildren) "/" "[Gmail]/All Mail"'
        result = _parse_list_response(line)
        assert result is not None
        assert result["name"] == "[Gmail]/All Mail"

    def test_parse_archive_special_use(self):
        line = b'(\\Archive) "/" Archive'
        result = _parse_list_response(line)
        assert result is not None
        assert result["special_use"] == "Archive"

    def test_parse_quoted_name(self):
        """Names with spaces or special chars are quoted."""
        line = b'(\\HasNoChildren) "/" "My Folder"'
        result = _parse_list_response(line)
        assert result is not None
        assert result["name"] == "My Folder"


# ── IMAPClient ───────────────────────────────────────────────────────────────


class TestIMAPClientInit:
    def test_init_defaults(self):
        client = IMAPClient("imap.example.com")
        assert client.host == "imap.example.com"
        assert client.port == 993
        assert client.use_ssl is True
        assert client._conn is None

    def test_init_non_default(self):
        client = IMAPClient("imap.example.com", port=143, use_ssl=False)
        assert client.port == 143
        assert client.use_ssl is False


class TestIMAPClientConnect:
    @patch("imaplib.IMAP4_SSL")
    def test_connect_ssl_success(self, mock_ssl):
        mock_conn = MagicMock()
        mock_ssl.return_value = mock_conn
        client = IMAPClient("imap.example.com", 993, use_ssl=True)
        client.connect("user@example.com", "secret")
        mock_ssl.assert_called_once_with("imap.example.com", 993, timeout=30)
        mock_conn.login.assert_called_once_with("user@example.com", "secret")

    @patch("imaplib.IMAP4")
    def test_connect_plain_success(self, mock_plain):
        mock_conn = MagicMock()
        mock_plain.return_value = mock_conn
        client = IMAPClient("imap.example.com", 143, use_ssl=False)
        client.connect("user", "pass")
        mock_plain.assert_called_once_with("imap.example.com", 143, timeout=30)

    @patch("imaplib.IMAP4_SSL")
    def test_connect_auth_failure(self, mock_ssl):
        from imaplib import IMAP4
        mock_conn = MagicMock()
        mock_conn.login.side_effect = IMAP4.error("Auth failed")
        mock_ssl.return_value = mock_conn
        client = IMAPClient("imap.example.com", 993)
        with pytest.raises(ConnectionError, match="IMAP authentication failed"):
            client.connect("user", "pass")

    @patch("imaplib.IMAP4_SSL", side_effect=TimeoutError("timed out"))
    def test_connect_timeout(self, mock_ssl):
        client = IMAPClient("imap.example.com", 993)
        with pytest.raises(ConnectionError, match="IMAP connection failed"):
            client.connect("user", "pass")


class TestIMAPClientConnProperty:
    def test_conn_raises_when_not_connected(self):
        client = IMAPClient("imap.example.com")
        with pytest.raises(RuntimeError, match="Not connected"):
            _ = client.conn

    def test_conn_returns_connection(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        assert client.conn is mock_conn


class TestIMAPClientDisconnect:
    def test_disconnect_when_connected(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        client.disconnect()
        mock_conn.logout.assert_called_once()
        assert client._conn is None

    def test_disconnect_when_not_connected(self):
        client = IMAPClient("imap.example.com")
        client.disconnect()  # Should not raise


class TestIMAPClientListFolders:
    def test_list_folders_empty(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.list.return_value = ("OK", [])
        result = client.list_folders()
        assert result == []

    def test_list_folders_not_ok(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.list.return_value = ("BAD", None)
        result = client.list_folders()
        assert result == []

    def test_list_folders_with_data(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" INBOX', b'(\\Sent) "/" Sent'],
        )
        result = client.list_folders()
        assert len(result) == 2
        assert result[0]["name"] == "INBOX"
        assert result[1]["name"] == "Sent"
        assert result[1]["special_use"] == "Sent"


class TestIMAPClientEnsureFolder:
    def test_ensure_folder_inserts(self):
        client = IMAPClient("imap.example.com")
        mock_db = MagicMock()
        client.ensure_folder("user@example.com", "INBOX", mock_db)
        mock_db.db.execute.assert_called_once()
        call_args = mock_db.db.execute.call_args[0]
        assert "INSERT OR IGNORE INTO folders" in call_args[0]

    def test_ensure_folder_returns_name(self):
        client = IMAPClient("imap.example.com")
        mock_db = MagicMock()
        result = client.ensure_folder("user@example.com", "INBOX", mock_db)
        assert result == "INBOX"


class TestIMAPClientCreateFolder:
    def test_create_folder_success(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.create.return_value = ("OK", [])
        assert client.create_folder("NewFolder") is True

    def test_create_folder_failure(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.create.return_value = ("NO", [b"Already exists"])
        assert client.create_folder("NewFolder") is False


class TestIMAPClientSelectFolder:
    def test_select_success(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [b"3"])
        assert client._select_folder("INBOX") is True
        mock_conn.select.assert_called_with("INBOX", readonly=False)

    def test_select_failure(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("NO", [b"Not found"])
        assert client._select_folder("INBOX") is False


class TestIMAPClientCopyMessage:
    def test_copy_success(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("OK", [])
        assert client.copy_message(42, "INBOX", "Archive") is True
        mock_conn.uid.assert_called_with("COPY", "42", "Archive")

    def test_copy_select_fail(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("NO", [])
        assert client.copy_message(42, "INBOX", "Archive") is False


class TestIMAPClientMoveMessage:
    def test_move_via_move(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("OK", [])
        assert client.move_message(42, "INBOX", "Trash") is True
        mock_conn.uid.assert_called_with("MOVE", "42", "Trash")

    def test_move_fallback(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])

        def uid_side_effect(cmd, *args):
            if cmd == "MOVE":
                from imaplib import IMAP4
                raise IMAP4.error("MOVE not supported")
            return ("OK", [])

        mock_conn.uid.side_effect = uid_side_effect
        assert client.move_message(42, "INBOX", "Trash") is True
        # Should have tried MOVE (fail), then COPY + STORE + EXPUNGE
        assert mock_conn.uid.call_count > 1

    def test_move_select_fail(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("NO", [])
        assert client.move_message(42, "INBOX", "Trash") is False


class TestIMAPClientDeleteMessage:
    def test_delete_success(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("OK", [])
        assert client.delete_message(42, "INBOX") is True
        mock_conn.uid.assert_called_with("STORE", "42", "+FLAGS", "(\\Deleted)")
        mock_conn.expunge.assert_called_once()

    def test_delete_select_fail(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("NO", [])
        assert client.delete_message(42, "INBOX") is False


class TestIMAPClientSetFlags:
    def test_set_flags_add(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("OK", [])
        assert client.set_flags(42, "INBOX", add=["\\Seen"]) is True
        mock_conn.uid.assert_called_with("STORE", "42", "+FLAGS.SILENT", "(\\Seen)")

    def test_set_flags_remove(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("OK", [])
        assert client.set_flags(42, "INBOX", remove=["\\Seen"]) is True
        mock_conn.uid.assert_called_with("STORE", "42", "-FLAGS.SILENT", "(\\Seen)")

    def test_set_flags_add_and_remove(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.side_effect = [("OK", []), ("OK", [])]
        assert client.set_flags(42, "INBOX", add=["\\Seen"], remove=["\\Flagged"]) is True
        assert mock_conn.uid.call_count == 2

    def test_set_flags_select_fail(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("NO", [])
        assert client.set_flags(42, "INBOX", add=["\\Seen"]) is False

    def test_set_flags_imap_error(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        from imaplib import IMAP4
        mock_conn.uid.side_effect = IMAP4.error("IMAP error")
        assert client.set_flags(42, "INBOX", add=["\\Seen"]) is False


# ── store_message ────────────────────────────────────────────────────────────


class TestStoreMessage:
    def _make_mock_db(self):
        db = MagicMock()
        db.execute_one.return_value = None
        db.execute.return_value = None
        return db

    def test_store_new_message(self):
        db = self._make_mock_db()
        data = {
            "subject": "Hello",
            "from_addr": "a@b.com",
            "body": "Test",
            "imap_uid": 42,
            "account_email": "user@example.com",
            "folder_name": "INBOX",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        msg_uuid = store_message(db, data, account_email="user@example.com", folder_name="INBOX")
        assert msg_uuid is not None

    def test_store_message_with_message_id_dedup(self):
        db = self._make_mock_db()
        db.execute_one.return_value = {"uuid": "existing-uuid", "is_read": 0, "is_starred": 0}
        data = {
            "subject": "Hello",
            "from_addr": "a@b.com",
            "message_id": "<msg-1@example.com>",
            "imap_uid": 42,
            "account_email": "user@example.com",
            "folder_name": "INBOX",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        msg_uuid = store_message(db, data, account_email="user@example.com", folder_name="INBOX")
        # Should return the existing UUID
        assert msg_uuid == "existing-uuid"

    def test_store_message_force_with_message_id(self):
        db = self._make_mock_db()
        db.execute_one.return_value = {"uuid": "existing-uuid", "is_read": 1, "is_starred": 0}
        data = {
            "subject": "Updated",
            "from_addr": "a@b.com",
            "message_id": "<msg-1@example.com>",
            "imap_uid": 42,
            "account_email": "user@example.com",
            "folder_name": "INBOX",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        msg_uuid = store_message(
            db, data, force=True,
            account_email="user@example.com", folder_name="INBOX",
        )
        assert msg_uuid == "existing-uuid"

    def test_store_message_with_uid_dedup(self):
        db = self._make_mock_db()

        def execute_one_side_effect(sql, params):
            # First call (message_id lookup) → None, Second call (UID lookup) → found
            if "message_id" in sql:
                return None
            if "imap_uid" in sql:
                return {"uuid": "uid-uuid", "is_read": 0, "is_starred": 0}
            return None

        db.execute_one.side_effect = execute_one_side_effect
        data = {
            "subject": "By UID",
            "from_addr": "a@b.com",
            "message_id": "",
            "imap_uid": 99,
            "account_email": "user@example.com",
            "folder_name": "INBOX",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        msg_uuid = store_message(db, data, account_email="user@example.com", folder_name="INBOX")
        assert msg_uuid == "uid-uuid"


# ── sync_folder ──────────────────────────────────────────────────────────────


class TestIMAPClientSyncFolder:
    def test_sync_folder_select_fail(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("NO", [])
        result = client.sync_folder("INBOX", "user@example.com", "INBOX", MagicMock())
        assert "errors" in result
        assert len(result["errors"]) == 1

    def test_sync_folder_no_new_uids(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [b"3"])
        mock_conn.uid.return_value = ("OK", [b"1 2 3"])
        mock_db = MagicMock()
        mock_db.db.execute.return_value = [{"imap_uid": 1}, {"imap_uid": 2}, {"imap_uid": 3}]
        result = client.sync_folder("INBOX", "user@example.com", "INBOX", mock_db)
        assert result["total"] == 3
        assert result["new"] == 0

    def test_sync_folder_fetch_error_handled(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [b"3"])
        mock_conn.uid.side_effect = [
            ("OK", [b"42 43"]),  # search
            ("BAD", []),  # fetch
        ]
        mock_db = MagicMock()
        mock_db.db.execute.return_value = []
        result = client.sync_folder("INBOX", "user@example.com", "INBOX", mock_db)
        assert result["total"] == 2
        # The fetch error should be recorded
        assert len(result["errors"]) >= 1

    def test_sync_folder_raises_on_outer_exception(self):
        """If an unexpected exception occurs during sync, it should be caught."""
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.side_effect = RuntimeError("Unexpected IMAP error")
        result = client.sync_folder("INBOX", "user@example.com", "INBOX", MagicMock())
        assert len(result["errors"]) == 1
        assert "Sync error" in result["errors"][0]
