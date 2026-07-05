"""Tests for lighterbird.email.imap.sync — _retry_pending_trash.

Covers: _retry_pending_trash with pending messages, successful move,
exception during move, no pending messages.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestRetryPendingTrash:
    """Tests for _retry_pending_trash — moving soft-deleted messages to IMAP Trash."""

    def _make_db_store(self, pending_rows=None):
        """Create a mock db_store with execute returning pending rows."""
        db = MagicMock()
        store = MagicMock()
        store.db = db

        if pending_rows:
            db.execute.return_value = pending_rows
        else:
            db.execute.return_value = []

        return store

    def test_no_pending_messages(self):
        """When no soft-deleted messages exist, should return early."""
        from lighterbird.email.imap.sync import _retry_pending_trash

        client = MagicMock()
        store = self._make_db_store()
        _retry_pending_trash(client, store, "test@example.com")
        client.move_message.assert_not_called()

    def test_moves_pending_message(self):
        """When pending messages exist, should move them to Trash."""
        from lighterbird.email.imap.sync import _retry_pending_trash

        pending = [
            {"uuid": "uuid-1", "imap_uid": 123, "folder_name": "INBOX"},
        ]
        client = MagicMock()
        client.move_message.return_value = True
        store = self._make_db_store(pending)

        _retry_pending_trash(client, store, "test@example.com")

        client.move_message.assert_called_once_with(123, "INBOX", "Trash")
        assert store.db.execute.call_count >= 2  # SELECT + UPDATE

    def test_move_fails_silently(self):
        """If move_message raises an exception, should catch and continue."""
        from lighterbird.email.imap.sync import _retry_pending_trash

        pending = [
            {"uuid": "uuid-1", "imap_uid": 123, "folder_name": "INBOX"},
        ]
        client = MagicMock()
        client.move_message.side_effect = Exception("IMAP error")
        store = self._make_db_store(pending)

        # Should not raise
        _retry_pending_trash(client, store, "test@example.com")
        client.move_message.assert_called_once()

    def test_skip_message_with_none_uid(self):
        """Messages with imap_uid=None should be skipped."""
        from lighterbird.email.imap.sync import _retry_pending_trash

        pending = [
            {"uuid": "uuid-1", "imap_uid": None, "folder_name": "INBOX"},
        ]
        client = MagicMock()
        store = self._make_db_store(pending)

        _retry_pending_trash(client, store, "test@example.com")
        client.move_message.assert_not_called()

    def test_skip_message_with_empty_folder(self):
        """Messages with empty folder_name should be skipped."""
        from lighterbird.email.imap.sync import _retry_pending_trash

        pending = [
            {"uuid": "uuid-1", "imap_uid": 123, "folder_name": None},
        ]
        client = MagicMock()
        store = self._make_db_store(pending)

        _retry_pending_trash(client, store, "test@example.com")
        client.move_message.assert_not_called()
