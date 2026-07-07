"""Tests for IMAP sync UIDVALIDITY checking."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.email.imap.sync import _check_uidvalidity
from lighterbird.email.db import get_db


@pytest.fixture
def db(tmp_path: Path):
    db = get_db(tmp_path / "email.db")
    now = "2026-01-01T00:00:00"
    # Insert account first (FK constraint)
    db.execute(
        "INSERT OR IGNORE INTO accounts "
        "(email, name, imap_server, smtp_server, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("test@example.com", "Test", "imap.example.com", "smtp.example.com", now, now),
    )
    db.execute(
        "INSERT INTO folders (account_email, name, uidvalidity, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("test@example.com", "INBOX", 12345, now, now),
    )
    db.execute(
        "INSERT INTO folders (account_email, name, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("test@example.com", "Sent", now, now),
    )
    return db


class TestCheckUIDValidity:
    def test_first_sync_stores_uidvalidity(self, db):
        """No stored UIDVALIDITY → store it."""
        _check_uidvalidity(db, "test@example.com", "Sent", 99999)
        row = db.execute_one(
            "SELECT uidvalidity FROM folders WHERE account_email = ? AND name = ?",
            ("test@example.com", "Sent"),
        )
        assert row["uidvalidity"] == 99999

    def test_same_uidvalidity_noop(self, db):
        """Same UIDVALIDITY → no changes."""
        msg_count_before = db.execute_one(
            "SELECT COUNT(*) AS c FROM messages"
        )["c"]
        _check_uidvalidity(db, "test@example.com", "INBOX", 12345)
        msg_count_after = db.execute_one(
            "SELECT COUNT(*) AS c FROM messages"
        )["c"]
        assert msg_count_before == msg_count_after

    def test_changed_uidvalidity_deletes_messages(self, db):
        """Different UIDVALIDITY → delete local messages for folder."""
        now = "2026-01-01T00:00:00"
        # Insert some messages in INBOX
        db.execute(
            "INSERT INTO messages (uuid, account_email, folder_name, imap_uid, "
            "subject, from_addr, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("m1", "test@example.com", "INBOX", 1, "A", "a@b.com", now, now),
        )
        db.execute(
            "INSERT INTO messages (uuid, account_email, folder_name, imap_uid, "
            "subject, from_addr, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("m2", "test@example.com", "INBOX", 2, "B", "c@d.com", now, now),
        )
        # And one in Sent (should not be affected)
        db.execute(
            "INSERT INTO messages (uuid, account_email, folder_name, imap_uid, "
            "subject, from_addr, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("m3", "test@example.com", "Sent", 3, "C", "e@f.com", now, now),
        )

        _check_uidvalidity(db, "test@example.com", "INBOX", 67890)

        # INBOX messages should be deleted
        inbox_count = db.execute_one(
            "SELECT COUNT(*) AS c FROM messages WHERE folder_name = 'INBOX'"
        )["c"]
        assert inbox_count == 0

        # Sent message should still exist
        sent_count = db.execute_one(
            "SELECT COUNT(*) AS c FROM messages WHERE folder_name = 'Sent'"
        )["c"]
        assert sent_count == 1

    def test_changed_uidvalidity_updates_folder(self, db):
        _check_uidvalidity(db, "test@example.com", "INBOX", 99999)
        row = db.execute_one(
            "SELECT uidvalidity FROM folders WHERE account_email = ? AND name = ?",
            ("test@example.com", "INBOX"),
        )
        assert row["uidvalidity"] == 99999

    def test_changed_uidvalidity_clears_backlog(self, db):
        """Backlog entries for the folder should also be deleted."""
        now = "2026-01-01T00:00:00"
        db.execute(
            "INSERT INTO _sync_backlog (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("b1", "test@example.com", "INBOX", 42, 1, 0, now),
        )
        db.execute(
            "INSERT INTO _sync_backlog (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("b2", "test@example.com", "Sent", 43, 0, 1, now),
        )

        _check_uidvalidity(db, "test@example.com", "INBOX", 67890)

        inbox_backlog = db.execute_one(
            "SELECT COUNT(*) AS c FROM _sync_backlog WHERE folder_name = 'INBOX'"
        )["c"]
        assert inbox_backlog == 0

        sent_backlog = db.execute_one(
            "SELECT COUNT(*) AS c FROM _sync_backlog WHERE folder_name = 'Sent'"
        )["c"]
        assert sent_backlog == 1
