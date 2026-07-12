"""Tests for sync/folder_mapper.py — FolderMapper."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lighterbird.email.sync.folder_mapper import FolderMapper


def _add_account(db, email: str) -> None:
    """Insert an account (FK requirement for folders)."""
    now = datetime.now(UTC).isoformat()
    db.execute(
        "INSERT OR IGNORE INTO accounts "
        "(email, name, imap_server, smtp_server, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (email, email, "imap.example.com", "smtp.example.com", now, now),
    )


@pytest.fixture
def db_with_folders(tmp_path: Path):
    """Create a database with sample folders."""
    from lighterbird.email.db import get_db

    db = get_db(tmp_path / "test.db")
    now = datetime.now(UTC).isoformat()

    for email in ["user@example.com", "simple@example.com", "empty@example.com"]:
        _add_account(db, email)

    # Insert folders with special_use
    db.execute(
        "INSERT INTO folders (account_email, name, special_use, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("user@example.com", "[Gmail]/Papierkorb", "\\Trash", now, now),
    )
    db.execute(
        "INSERT INTO folders (account_email, name, special_use, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("user@example.com", "[Gmail]/Gesendet", "\\Sent", now, now),
    )
    db.execute(
        "INSERT INTO folders (account_email, name, special_use, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("user@example.com", "INBOX", None, now, now),
    )

    # Account with no special_use — just a regular Trash folder
    db.execute(
        "INSERT INTO folders (account_email, name, special_use, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("simple@example.com", "Trash", None, now, now),
    )
    db.execute(
        "INSERT INTO folders (account_email, name, special_use, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("simple@example.com", "Sent", None, now, now),
    )

    # Account with no folders at all
    db.execute(
        "INSERT INTO folders (account_email, name, special_use, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("empty@example.com", "INBOX", None, now, now),
    )

    return db


class TestFolderMapper:
    def test_resolve_trash_via_special_use(self, db_with_folders):
        """Should return localized name via SPECIAL-USE flag."""
        mapper = FolderMapper(db_with_folders)
        assert mapper.resolve_trash("user@example.com") == "[Gmail]/Papierkorb"

    def test_resolve_trash_via_alias(self, db_with_folders):
        """Should find 'Trash' via alias list."""
        mapper = FolderMapper(db_with_folders)
        assert mapper.resolve_trash("simple@example.com") == "Trash"

    def test_resolve_trash_fallback(self, db_with_folders):
        """Should return literal 'Trash' as fallback."""
        mapper = FolderMapper(db_with_folders)
        assert mapper.resolve_trash("empty@example.com") == "Trash"

    def test_resolve_sent_via_special_use(self, db_with_folders):
        mapper = FolderMapper(db_with_folders)
        assert mapper.resolve_sent("user@example.com") == "[Gmail]/Gesendet"

    def test_resolve_sent_alias(self, db_with_folders):
        mapper = FolderMapper(db_with_folders)
        assert mapper.resolve_sent("simple@example.com") == "Sent"

    def test_resolve_junk_fallback(self, db_with_folders):
        mapper = FolderMapper(db_with_folders)
        assert mapper.resolve_junk("user@example.com") == "Junk"

    def test_detect_stale_folder_exists(self, db_with_folders):
        mapper = FolderMapper(db_with_folders)
        assert mapper.detect_stale_folder("user@example.com", "INBOX") is False

    def test_detect_stale_folder_not_found(self, db_with_folders):
        mapper = FolderMapper(db_with_folders)
        assert mapper.detect_stale_folder("user@example.com", "NONEXISTENT") is True

    # ── Drafts ────────────────────────────────────────────────────────

    def test_resolve_drafts_via_special_use(self, db_with_folders):
        """Should return localized name via SPECIAL-USE flag."""
        from datetime import UTC, datetime
        now = datetime.now(UTC).isoformat()
        db_with_folders.execute(
            "INSERT INTO folders (account_email, name, special_use, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("user@example.com", "[Gmail]/Drafts", "\\Drafts", now, now),
        )
        mapper = FolderMapper(db_with_folders)
        assert mapper.resolve_drafts("user@example.com") == "[Gmail]/Drafts"

    def test_resolve_drafts_alias(self, db_with_folders):
        """Should find a Drafts alias (e.g. 'Entwürfe') by name."""
        from datetime import UTC, datetime
        now = datetime.now(UTC).isoformat()
        db_with_folders.execute(
            "INSERT INTO folders (account_email, name, special_use, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("simple@example.com", "Entwürfe", None, now, now),
        )
        mapper = FolderMapper(db_with_folders)
        assert mapper.resolve_drafts("simple@example.com") == "Entwürfe"

    def test_resolve_drafts_fallback(self, db_with_folders):
        """Should return literal 'Drafts' as fallback."""
        mapper = FolderMapper(db_with_folders)
        assert mapper.resolve_drafts("empty@example.com") == "Drafts"
