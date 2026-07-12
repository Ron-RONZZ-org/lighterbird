"""Dead-letter service — tracks backlog entries that exceeded retry limits.

Entries that cannot be processed after ``MAX_RETRIES`` attempts are moved
to the ``_dead_letters`` table for manual inspection and optional clearance.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class DeadLetterService:
    """Manage the _dead_letters table.

    The dead-letter table stores backlog entries that exhausted their
    retry budget.  These entries are preserved for manual review via
    CLI or API and can be cleared individually or in bulk.

    Args:
        db: Database connection (LighterbirdDB).
    """

    def __init__(self, db: Any):
        self.db = db

    def auto_dead(self, entry: dict, reason: str) -> None:
        """Move a backlog entry to the dead-letter table.

        Deletes the entry from _sync_backlog and inserts it into
        _dead_letters with the current timestamp and reason.

        Args:
            entry: The backlog entry dict (must contain ``id``).
            reason: Human-readable reason for dead-letter escalation.
        """
        now = datetime.now(UTC).isoformat()
        entry_id = entry.get("id")
        if entry_id is None:
            logger.warning("[dead_letter] Cannot dead-letter entry without id: %s", entry)
            return

        self.db.execute(
            "INSERT INTO _dead_letters "
            "(msg_uuid, account_email, folder_name, imap_uid, "
            " is_read, is_deleted, operation,"
            " created_at, last_attempt, retries,"
            " dead_at, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.get("msg_uuid", ""),
                entry.get("account_email", ""),
                entry.get("folder_name"),
                entry.get("imap_uid"),
                entry.get("is_read", 0),
                entry.get("is_deleted", 0),
                entry.get("operation", "sync"),
                entry.get("created_at", now),
                entry.get("last_attempt") or now,
                entry.get("retries", 0),
                now,
                reason,
            ),
        )
        self.db.execute("DELETE FROM _sync_backlog WHERE id = ?", (entry_id,))
        logger.info(
            "[dead_letter] Entry %s (msg %s) dead-lettered: %s",
            entry_id, entry.get("msg_uuid", "")[:8], reason,
        )

    def list(self, account_email: str | None = None) -> list[dict[str, Any]]:
        """List dead-letter entries.

        Args:
            account_email: If provided, only list entries for this account.

        Returns:
            List of dead-letter entry dicts.
        """
        if account_email:
            return list(self.db.execute(
                "SELECT * FROM _dead_letters WHERE account_email = ? "
                "ORDER BY dead_at DESC", (account_email,),
            ))
        return list(self.db.execute(
            "SELECT * FROM _dead_letters ORDER BY dead_at DESC"
        ))

    def count(self, account_email: str | None = None) -> int:
        """Count dead-letter entries.

        Args:
            account_email: If provided, only count for this account.
        """
        if account_email:
            row = self.db.execute_one(
                "SELECT COUNT(*) AS cnt FROM _dead_letters WHERE account_email = ?",
                (account_email,),
            )
        else:
            row = self.db.execute_one("SELECT COUNT(*) AS cnt FROM _dead_letters")
        return row["cnt"] if row else 0

    def clear(self, entry_id: int | None = None,
              account_email: str | None = None) -> int:
        """Clear dead-letter entries.

        Args:
            entry_id: Specific entry to clear.  If None, clears all
                      (optionally filtered by account_email).
            account_email: Only clear entries for this account
                           (only applies when entry_id is None).

        Returns:
            Number of entries cleared.
        """
        if entry_id is not None:
            self.db.execute("DELETE FROM _dead_letters WHERE id = ?", (entry_id,))
            return 1
        if account_email:
            self.db.execute(
                "DELETE FROM _dead_letters WHERE account_email = ?",
                (account_email,),
            )
        else:
            self.db.execute("DELETE FROM _dead_letters")
        return self.db.total_changes if hasattr(self.db, 'total_changes') else -1

    def retry_entry(self, entry_id: int) -> bool:
        """Move a dead-letter entry back to the sync backlog for retry.

        Args:
            entry_id: The dead-letter entry to retry.

        Returns:
            True if the entry was moved, False if not found.
        """
        entry = self.db.execute_one(
            "SELECT * FROM _dead_letters WHERE id = ?", (entry_id,),
        )
        if not entry:
            return False

        now_str = datetime.now(UTC).isoformat()
        self.db.execute(
            "INSERT INTO _sync_backlog "
            "(msg_uuid, account_email, folder_name, imap_uid, "
            " is_read, is_deleted, operation, created_at, last_attempt, retries) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                entry.get("msg_uuid", ""),
                entry.get("account_email", ""),
                entry.get("folder_name"),
                entry.get("imap_uid"),
                entry.get("is_read", 0),
                entry.get("is_deleted", 0),
                entry.get("operation", "sync"),
                entry.get("created_at", now_str),
                now_str,
            ),
        )
        self.db.execute("DELETE FROM _dead_letters WHERE id = ?", (entry_id,))
        logger.info(
            "[dead_letter] Entry %s retried back to backlog", entry_id,
        )
        return True


__all__ = ["DeadLetterService"]
