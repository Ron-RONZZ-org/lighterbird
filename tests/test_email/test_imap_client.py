"""Tests for email/imap/client.py — IMAPClient, _parse_list_response, store_message."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.email.imap.client import (
    IMAPClient,
    _parse_list_response,
    _to_imap_date,
)
from lighterbird.email.imap.storage import store_message

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

    def test_parse_extended_response_with_extra(self):
        """Some servers include extra response codes after the mailbox name."""
        line = b'(\\HasNoChildren) "/" INBOX (MYRIGHTS "acdelrx")'
        result = _parse_list_response(line)
        assert result is not None
        assert result["name"] == "INBOX"
        assert result["delimiter"] == "/"

    def test_parse_non_ascii_utf8_name(self):
        """Non-ASCII UTF-8 folder names (quoted)."""
        line = b'(\\HasNoChildren) "/" "NON-ASCII/\xe3\x83\x95\xe3\x82\xa9\xe3\x83\xab\xe3\x83\x80"'
        result = _parse_list_response(line)
        assert result is not None
        # Decoded: NON-ASCII/フォルダ
        assert "NON-ASCII/" in result["name"]

    def test_parse_fallback_quoted_name_no_regex(self):
        """Fallback parser should handle a line where the regex does not match
        but the name is still extractable by splitting on quotes.
        Simulates a non-standard IMAP server."""
        # Line without the standard * LIST prefix (already stripped by imaplib)
        # but with extra data after the name that confuses the regex
        line = b'(\\HasNoChildren) "/" "My Custom Folder" extra data'
        result = _parse_list_response(line)
        # Should still parse via fallback
        assert result is not None
        assert result["name"] == "My Custom Folder"
        assert result["delimiter"] == "/"

    def test_parse_fallback_unquoted_name_with_spaces_noregex(self):
        """Fallback when regex does not match and server sends unquoted name with spaces."""
        # Line format: flags delimiter name (all unquoted, name with spaces)
        # The regex cannot match this because it expects \S+ for unquoted.
        # But the fallback split-on-quotes won't capture this either (no quotes).
        # This should still return something sensible (the first word via regex).
        line = b'(\\HasNoChildren) "/" My Folder With Spaces'
        result = _parse_list_response(line)
        # The regex matches partially and returns "My"
        # This is expected behavior — the server is non-compliant for not quoting
        assert result is not None
        assert result["name"] == "My"

    def test_parse_extended_list_with_trailing_parens(self):
        """Extended LIST responses with trailing parenthesized data."""
        line = b'(\\HasNoChildren) "/" INBOX (SOMEEXTENSION ("data"))'
        result = _parse_list_response(line)
        assert result is not None
        assert result["name"] == "INBOX"

    def test_parse_quoted_name_with_trailing_extra(self):
        """Quoted name followed by extra data (server may add response codes)."""
        line = b'(\\HasNoChildren) "/" "My Folder" (extra)'
        result = _parse_list_response(line)
        assert result is not None
        assert result["name"] == "My Folder"

    def test_parse_fallback_deeply_nested(self):
        """Deeply nested folder path with spaces (quoted)."""
        line = b'(\\HasNoChildren) "." "Parent Folder/Child Folder/Sub Folder"'
        result = _parse_list_response(line)
        assert result is not None
        assert result["name"] == "Parent Folder/Child Folder/Sub Folder"
        assert result["delimiter"] == "."

    def test_parse_with_childinfo(self):
        """LIST response with CHILDINFO extension (RFC 5258)."""
        line = b'(\\HasChildren) "/" INBOX (CHILDINFO ("SUBSCRIBED"))'
        result = _parse_list_response(line)
        assert result is not None
        assert result["name"] == "INBOX"

    def test_parse_empty_flags(self):
        """Empty flags parenthesized list."""
        line = b'() "/" INBOX'
        result = _parse_list_response(line)
        assert result is not None
        assert result["name"] == "INBOX"
        assert result["flags"] == []

    def test_parse_nil_delimiter(self):
        """NIL delimiter (server-side root)."""
        line = b'(\\Noselect) NIL "" '
        result = _parse_list_response(line)
        # Empty name after decode → returns None
        assert result is None


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

    def test_list_folders_skips_unparseable(self):
        """list_folders should skip unparseable lines and log a warning."""
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        # Mix parseable and unparseable lines
        mock_conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" INBOX',
                b'garbage that cannot be parsed',
                b'(\\Sent) "/" Sent',
            ],
        )
        result = client.list_folders()
        # Should skip the garbage line, keep the two valid ones
        assert len(result) == 2
        names = [r["name"] for r in result]
        assert "INBOX" in names
        assert "Sent" in names

    def test_list_folders_handles_extended_format(self):
        """list_folders should handle extended LIST formats regardless of
        whether they use the regex or fallback path."""
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" INBOX (MYRIGHTS "acdelrx")',
                b'(\\HasNoChildren) "/" "My Folder" extra data at end',
            ],
        )
        result = client.list_folders()
        assert len(result) == 2
        names = [r["name"] for r in result]
        assert "INBOX" in names
        # The fallback should extract the folder name even with extra data
        folder_names = [r["name"] for r in result]
        assert any("My Folder" in n for n in folder_names)


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
            "received_at": datetime.now(UTC).isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
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
            "received_at": datetime.now(UTC).isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
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
            "received_at": datetime.now(UTC).isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
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
            "received_at": datetime.now(UTC).isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
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


# ── _to_imap_date ──────────────────────────────────────────────────────────


class TestToImapDate:
    def test_iso_to_imap(self):
        assert _to_imap_date("2024-01-01") == "01-Jan-2024"

    def test_iso_to_imap_june(self):
        assert _to_imap_date("2024-06-15") == "15-Jun-2024"

    def test_iso_to_imap_december(self):
        assert _to_imap_date("2023-12-25") == "25-Dec-2023"

    def test_invalid_format_returns_original(self):
        assert _to_imap_date("not-a-date") == "not-a-date"

    def test_empty_string_returns_original(self):
        assert _to_imap_date("") == ""

    def test_none_returns_none(self):
        assert _to_imap_date(None) is None


# ── IMAPClient.search_remote ──────────────────────────────────────────────────


class TestIMAPClientSearchRemote:
    def test_search_remote_empty_query_no_criteria(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        result = client.search_remote("INBOX", "")
        assert result == []

    def test_search_remote_calls_uid_search(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("OK", [b"1 2 3"])
        result = client.search_remote("INBOX", "meeting")
        assert result == [1, 2, 3]
        mock_conn.select.assert_called_with("INBOX", readonly=True)
        mock_conn.uid.assert_called_once()

    def test_search_remote_with_criteria(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("OK", [b"42 99"])
        result = client.search_remote(
            "INBOX", "project",
            criteria={"from_": "alice", "subject": "report", "after": "2024-01-01"},
        )
        assert result == [42, 99]
        # Verify the SEARCH command includes FROM, SUBJECT, SINCE
        call_args = mock_conn.uid.call_args[0]
        assert "FROM" in str(call_args)
        assert "SUBJECT" in str(call_args)
        assert "SINCE" in str(call_args)
        assert "01-Jan-2024" in str(call_args)  # Converted from ISO

    def test_search_remote_to_and_cc(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("OK", [b"7"])
        result = client.search_remote("INBOX", "", criteria={"to": "bob", "cc": "carol"})
        assert result == [7]
        cmd = str(mock_conn.uid.call_args[0])
        assert 'TO "bob"' in cmd
        assert 'CC "carol"' in cmd

    def test_search_remote_participant(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("OK", [b"5"])
        result = client.search_remote("INBOX", "", criteria={"participant": "dave"})
        assert result == [5]
        cmd = str(mock_conn.uid.call_args[0])
        assert "FROM" in cmd
        assert "TO" in cmd
        assert "CC" in cmd
        assert "dave" in cmd

    def test_search_remote_select_failure_returns_empty(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("NO", [])
        # When select fails, UID SEARCH also fails → returns empty list
        result = client.search_remote("INBOX", "test")
        assert result == []

    def test_search_remote_uid_search_failure_returns_empty(self):
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("BAD", [])
        result = client.search_remote("INBOX", "test")
        assert result == []

    def test_search_remote_date_conversion(self):
        """Verify ISO dates are converted to IMAP format in the command."""
        client = IMAPClient("imap.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        mock_conn.select.return_value = ("OK", [])
        mock_conn.uid.return_value = ("OK", [b"1"])
        client.search_remote("INBOX", "", criteria={"after": "2024-03-15", "before": "2024-04-20"})
        cmd = str(mock_conn.uid.call_args[0])
        assert "15-Mar-2024" in cmd
        assert "20-Apr-2024" in cmd
