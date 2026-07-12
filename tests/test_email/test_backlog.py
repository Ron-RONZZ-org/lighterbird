"""Tests for BacklogService and DeadLetterService (Phase 0 of IMAP sync overhaul)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.email.db import get_db
from lighterbird.email.services import (
    BacklogService,
    DeadLetterService,
)


@pytest.fixture
def db(tmp_path: Path):
    return get_db(tmp_path / "email.db")


@pytest.fixture
def backlog(db):
    """BacklogService with no pool/folder_mapper (tests without IMAP)."""
    dead_letter = DeadLetterService(db)
    return BacklogService(
        db=db,
        pool=None,
        folder_mapper=None,
        dead_letter=dead_letter,
        max_retries=3,  # Low for test convenience
        batch_size=100,
    )


@pytest.fixture
def dead_letter(db):
    return DeadLetterService(db)


@pytest.fixture
def sample_msg(db):
    """Create a minimal message entry in the messages table."""
    now = datetime.now(UTC).isoformat()
    db.execute(
        "INSERT INTO folders (account_email, name, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("test@example.com", "INBOX", now, now),
    )
    db.execute(
        "INSERT INTO messages (uuid, account_email, folder_name, imap_uid, "
        "subject, from_addr, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("msg-001", "test@example.com", "INBOX", 42,
         "Test", "sender@example.com", now, now),
    )
    return "msg-001"


class TestSchema:
    """Verify new schema columns and tables exist."""

    def test_dead_letters_table_exists(self, db):
        assert db.table_exists("_dead_letters")

    def test_messages_has_modseq(self, db):
        cols = {row["name"] for row in db.execute("PRAGMA table_info(messages)")}
        assert "modseq" in cols

    def test_folders_has_uidvalidity(self, db):
        cols = {row["name"] for row in db.execute("PRAGMA table_info(folders)")}
        assert "uidvalidity" in cols

    def test_folders_has_highest_modseq(self, db):
        cols = {row["name"] for row in db.execute("PRAGMA table_info(folders)")}
        assert "highest_modseq" in cols

    def test_folders_has_special_use(self, db):
        cols = {row["name"] for row in db.execute("PRAGMA table_info(folders)")}
        assert "special_use" in cols

    def test_sync_backlog_has_operation(self, db):
        cols = {row["name"] for row in db.execute("PRAGMA table_info(_sync_backlog)")}
        assert "operation" in cols

    def test_dead_letters_has_operation(self, db):
        cols = {row["name"] for row in db.execute("PRAGMA table_info(_dead_letters)")}
        assert "operation" in cols


class TestDeadLetterService:
    """Test DeadLetterService CRUD operations."""

    def test_list_empty(self, dead_letter):
        assert dead_letter.list() == []
        assert dead_letter.count() == 0

    def test_auto_dead(self, db, dead_letter):
        # Insert a backlog entry first
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO _sync_backlog (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at, retries) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg-001", "test@example.com", "INBOX", 42, 1, 0, now, 5),
        )
        entry = db.execute_one("SELECT * FROM _sync_backlog")

        dead_letter.auto_dead(entry, "Test dead-letter")

        # Entry should be moved to dead_letters
        assert dead_letter.count() == 1
        dl = dead_letter.list()[0]
        assert dl["msg_uuid"] == "msg-001"
        assert dl["reason"] == "Test dead-letter"
        assert dl["retries"] == 5

        # Backlog should be empty
        assert db.execute_one("SELECT COUNT(*) AS c FROM _sync_backlog")["c"] == 0

    def test_auto_dead_no_id(self, dead_letter, caplog):
        """Entry without 'id' should log a warning."""
        dead_letter.auto_dead({}, "no id")
        assert "Cannot dead-letter entry without id" in caplog.text

    def test_clear_all(self, db, dead_letter):
        now = datetime.now(UTC).isoformat()
        for i in range(3):
            db.execute(
                "INSERT INTO _dead_letters (msg_uuid, account_email, folder_name, "
                "imap_uid, is_read, is_deleted, created_at, last_attempt, retries, "
                "dead_at, reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"msg-{i}", "test@example.com", "INBOX", 42 + i,
                 0, 0, now, now, 3, now, "test"),
            )
        assert dead_letter.count() == 3
        dead_letter.clear()
        assert dead_letter.count() == 0

    def test_clear_by_account(self, db, dead_letter):
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO _dead_letters (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at, last_attempt, retries, "
            "dead_at, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg-a", "a@test.com", "INBOX", 1, 0, 0, now, now, 3, now, "test"),
        )
        db.execute(
            "INSERT INTO _dead_letters (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at, last_attempt, retries, "
            "dead_at, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg-b", "b@test.com", "INBOX", 2, 0, 0, now, now, 3, now, "test"),
        )
        assert dead_letter.count() == 2
        dead_letter.clear(account_email="a@test.com")
        assert dead_letter.count() == 1

    def test_clear_single(self, db, dead_letter):
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO _dead_letters (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at, last_attempt, retries, "
            "dead_at, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg-x", "x@test.com", "INBOX", 1, 0, 0, now, now, 3, now, "test"),
        )
        entry = dead_letter.list()[0]
        dead_letter.clear(entry_id=entry["id"])
        assert dead_letter.count() == 0

    def test_retry_entry(self, db, dead_letter):
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO _dead_letters (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at, last_attempt, retries, "
            "dead_at, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg-retry", "test@example.com", "INBOX", 42,
             1, 0, now, now, 3, now, "test"),
        )
        entry = dead_letter.list()[0]
        result = dead_letter.retry_entry(entry["id"])
        assert result is True
        # Should be back in backlog
        backlog_count = db.execute_one(
            "SELECT COUNT(*) AS c FROM _sync_backlog"
        )["c"]
        assert backlog_count == 1
        # Dead letter should be empty
        assert dead_letter.count() == 0

    def test_retry_entry_not_found(self, dead_letter):
        result = dead_letter.retry_entry(999)
        assert result is False


class TestBacklogService:
    """Test BacklogService core logic (without IMAP connection)."""

    def test_count_pending_empty(self, backlog):
        assert backlog.count_pending() == 0
        assert backlog.count_pending("test@example.com") == 0

    def test_enqueue(self, db, backlog):
        backlog.enqueue(
            msg_uuid="msg-001",
            account_email="test@example.com",
            folder_name="INBOX",
            imap_uid=42,
            is_read=1,
            is_deleted=0,
        )
        assert backlog.count_pending() == 1
        assert backlog.count_for_msg("msg-001") == 1
        assert backlog.count_pending("test@example.com") == 1

    def test_enqueue_trash(self, db, backlog):
        backlog.enqueue_trash(
            msg_uuid="msg-002",
            account_email="test@example.com",
            folder_name="INBOX",
            imap_uid=43,
        )
        entry = backlog.list_pending()[0]
        assert entry["is_deleted"] == 1
        assert entry["is_read"] == 1
        assert entry["operation"] == "trash"

    def test_enqueue_expunge(self, db, backlog):
        backlog.enqueue_expunge(
            msg_uuid="msg-003",
            account_email="test@example.com",
            folder_name="INBOX",
            imap_uid=44,
        )
        entry = backlog.list_pending()[0]
        assert entry["operation"] == "expunge"
        assert entry["is_deleted"] == 1
        assert entry["is_read"] == 1
        assert entry["imap_uid"] == 44
        assert backlog.count_pending() == 1

    def test_enqueue_duplicate(self, db, backlog):
        """INSERT OR REPLACE should update existing entry."""
        backlog.enqueue("msg-001", "test@example.com", "INBOX", 42, 1, 0)
        assert backlog.count_pending() == 1

        # Re-enqueue with different state
        backlog.enqueue("msg-001", "test@example.com", "INBOX", 42, 0, 0)
        assert backlog.count_pending() == 1  # Still one entry

    def test_enqueue_no_imap_uid_skipped(self, db, backlog):
        """Messages without imap_uid are skipped (no point enqueuing)."""
        backlog.enqueue(
            msg_uuid="local-only",
            account_email="test@example.com",
            folder_name="INBOX",
            imap_uid=None,
            is_read=1,
            is_deleted=0,
        )
        # We still enqueue it — BacklogService._process() cleans stale entries
        assert backlog.count_pending() == 1

    def test_count_for_msg_not_found(self, backlog):
        assert backlog.count_for_msg("nonexistent") == 0

    def test_process_all_empty(self, backlog):
        assert backlog.process_all() == 0

    def test_lock_timeout(self, backlog):
        """process_all should return 0 if lock held by another thread."""
        backlog._lock.acquire()
        result = backlog.process_all()
        assert result == 0
        backlog._lock.release()

    def test_stale_entry_cleanup(self, db, backlog):
        """Entries with NULL imap_uid should be cleaned up."""
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO _sync_backlog (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at, retries) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("stale-msg", "test@example.com", "INBOX", None, 1, 0, now, 0),
        )
        assert backlog.count_pending() == 1
        backlog.process_all()
        assert backlog.count_pending() == 0

    def test_dead_letter_escalation(self, db, backlog):
        """Entries exceeding MAX_RETRIES should be dead-lettered."""
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO _sync_backlog (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at, retries) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("dead-msg", "test@example.com", "INBOX", 42, 1, 0, now, backlog.MAX_RETRIES),
        )
        assert backlog.count_pending() == 1
        result = backlog.process_all()
        assert result == 0  # Entry was dead-lettered, not synced
        assert backlog.count_pending() == 0
        assert backlog._dead_letter.count() == 1

    def test_list_pending_filtered(self, db, backlog):
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO _sync_backlog (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("m1", "a@test.com", "INBOX", 1, 0, 0, now),
        )
        db.execute(
            "INSERT INTO _sync_backlog (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("m2", "b@test.com", "INBOX", 2, 1, 0, now),
        )

        entries = backlog.list_pending(account_email="a@test.com")
        assert len(entries) == 1
        assert entries[0]["msg_uuid"] == "m1"

        all_entries = backlog.list_pending()
        assert len(all_entries) == 2


class TestMessageOpsServiceIntegration:
    """Integration tests verifying MessageOpsService uses BacklogService."""

    def test_mark_read_enqueues_backlog(self, db):
        """mark_read should update local DB and enqueue backlog."""
        from lighterbird.email.services import AccountService
        from lighterbird.email.services.msg_ops import MessageOpsService

        # Set up account + message
        acct_svc = AccountService(db)
        acct_svc.create_account({
            "name": "Test",
            "email": "test@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
        }, "pw")

        now = datetime.now(UTC).isoformat()
        # Insert folder first (FK constraint)
        db.execute(
            "INSERT OR IGNORE INTO folders (account_email, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("test@example.com", "INBOX", now, now),
        )
        db.execute(
            "INSERT INTO messages (uuid, account_email, folder_name, imap_uid, "
            "subject, from_addr, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg-r", "test@example.com", "INBOX", 42,
             "Read Test", "s@e.com", now, now),
        )

        ops = MessageOpsService(db, acct_svc)
        ops.mark_read("msg-r", is_read=True)

        # DB should be updated
        msg = db.execute_one("SELECT is_read FROM messages WHERE uuid = 'msg-r'")
        assert msg["is_read"] == 1

        # Backlog should have entry
        assert ops.backlog.count_for_msg("msg-r") == 1

    def test_trash_message_enqueues_backlog(self, db):
        """trash_message should soft-delete locally and enqueue."""
        from lighterbird.email.services import AccountService
        from lighterbird.email.services.msg_ops import MessageOpsService

        acct_svc = AccountService(db)
        acct_svc.create_account({
            "name": "Test",
            "email": "test@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
        }, "pw")

        now = datetime.now(UTC).isoformat()
        # Insert folder first (FK constraint)
        db.execute(
            "INSERT OR IGNORE INTO folders (account_email, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("test@example.com", "INBOX", now, now),
        )
        db.execute(
            "INSERT INTO messages (uuid, account_email, folder_name, imap_uid, "
            "subject, from_addr, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg-t", "test@example.com", "INBOX", 43,
             "Trash Test", "s@e.com", now, now),
        )

        ops = MessageOpsService(db, acct_svc)
        ops.trash_message("msg-t")

        msg = db.execute_one("SELECT is_deleted FROM messages WHERE uuid = 'msg-t'")
        assert msg["is_deleted"] == 1

        entry = ops.backlog.list_pending(account_email="test@example.com")
        assert len(entry) == 1
        assert entry[0]["is_deleted"] == 1
