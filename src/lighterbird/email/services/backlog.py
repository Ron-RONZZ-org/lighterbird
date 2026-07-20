"""Backlog service — _sync_backlog CRUD and batch processing.

Extracted from :mod:`msg_ops` as part of the IMAP sync engine overhaul
(Phase 0).  Provides backlog enqueue, batch processing with connection
pooling, retry tracking, and dead-letter escalation.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Backlog operation types
BacklogOperation = Literal["sync", "trash", "expunge"]


class BacklogLockError(Exception):
    """Another thread is already processing the backlog."""


class BacklogService:
    """Manage the _sync_backlog table for deferred IMAP operations.

    Supports three operation types:

    * ``sync`` — flag sync (\\Seen, \\Deleted) — the original/default.
    * ``trash`` — move message to the IMAP Trash folder (UID MOVE / COPY+EXPUNGE).
    * ``expunge`` — permanently delete from the IMAP server
      (STORE +FLAGS.SILENT (\\Deleted) + EXPUNGE).  No local DB update
      because the calling code (e.g. ``hard_delete_message``) already
      removed the local row before enqueuing.

    Thread-safe: uses a ``threading.Lock`` to serialize backlog processing.
    Lock acquisition has a timeout; if busy, the caller should retry
    rather than block.

    Args:
        db: Database connection (LighterDB).
        pool: IMAP connection pool for per-account reuse.
        folder_mapper: Folder name resolution service.
        dead_letter: Dead-letter service for entries exceeding max retries.
        max_retries: Maximum attempts before dead-letter escalation.
        batch_size: Max backlog entries to process per call.
    """

    MAX_RETRIES: int = 10
    BATCH_SIZE: int = 200

    def __init__(
        self,
        db: Any,
        pool: Any | None = None,
        folder_mapper: Any | None = None,
        dead_letter: Any | None = None,
        max_retries: int = 10,
        batch_size: int = 200,
    ):
        self.db = db
        self._pool = pool
        self._folder_mapper = folder_mapper
        self._dead_letter = dead_letter
        self.MAX_RETRIES = max_retries
        self.BATCH_SIZE = batch_size
        self._lock = threading.Lock()

    # ── Enqueue ───────────────────────────────────────────────────────────

    def enqueue(
        self,
        msg_uuid: str,
        account_email: str,
        folder_name: str | None,
        imap_uid: int | None,
        is_read: int,
        is_deleted: int,
        operation: BacklogOperation = "sync",
    ) -> None:
        """Queue a message operation for later processing.

        Uses INSERT OR REPLACE so that re-enqueueing the same msg_uuid
        updates the existing entry rather than creating a duplicate.

        Args:
            msg_uuid: Message UUID.
            account_email: Account email.
            folder_name: Folder name on the IMAP server.
            imap_uid: IMAP UID of the message.
            is_read: 1 if the message is read / \\Seen.
            is_deleted: 1 if the message is flagged \\Deleted.
            operation: Operation type — ``"sync"`` (flag sync, default),
                ``"trash"`` (move to Trash folder), or ``"expunge"``
                (permanent IMAP deletion).
        """
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "INSERT OR REPLACE INTO _sync_backlog "
            "(id, msg_uuid, account_email, folder_name, imap_uid, "
            " is_read, is_deleted, operation, created_at, last_attempt, retries) "
            "VALUES ("
            "  COALESCE((SELECT id FROM _sync_backlog WHERE msg_uuid = ?), NULL),"
            "  ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0"
            ")",
            (msg_uuid, msg_uuid, account_email, folder_name, imap_uid,
             is_read, is_deleted, operation, now),
        )

    def enqueue_trash(
        self,
        msg_uuid: str,
        account_email: str,
        folder_name: str | None,
        imap_uid: int | None,
    ) -> None:
        """Queue a message for deferred IMAP trash move.

        Shortcut for :meth:`enqueue` with ``operation='trash'``.
        """
        self.enqueue(msg_uuid, account_email, folder_name, imap_uid,
                     is_read=1, is_deleted=1, operation="trash")

    def enqueue_expunge(
        self,
        msg_uuid: str,
        account_email: str,
        folder_name: str | None,
        imap_uid: int | None,
    ) -> None:
        """Queue a message for deferred IMAP permanent deletion (EXPUNGE).

        The calling code (e.g. ``hard_delete_message``) MUST remove the
        local DB row **before** calling this method.  The backlog
        processor will connect to IMAP, mark the UID as \\Deleted, and
        EXPUNGE the folder, then delete the backlog entry.  No local DB
        update is performed because the row no longer exists.

        Shortcut for :meth:`enqueue` with ``operation='expunge'``.
        """
        self.enqueue(msg_uuid, account_email, folder_name, imap_uid,
                     is_read=1, is_deleted=1, operation="expunge")

    # ── Queries ───────────────────────────────────────────────────────────

    def count_pending(self, account_email: str | None = None) -> int:
        """Count pending backlog entries, optionally filtered by account."""
        if account_email:
            row = self.db.execute_one(
                "SELECT COUNT(*) AS cnt FROM _sync_backlog "
                "WHERE account_email = ?", (account_email,),
            )
        else:
            row = self.db.execute_one("SELECT COUNT(*) AS cnt FROM _sync_backlog")
        return row["cnt"] if row else 0

    def count_for_msg(self, msg_uuid: str) -> int:
        """Check if a specific message has a pending backlog entry."""
        row = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM _sync_backlog WHERE msg_uuid = ?",
            (msg_uuid,),
        )
        return row["cnt"] if row else 0

    def list_pending(self, account_email: str | None = None,
                     limit: int = 500) -> list[dict[str, Any]]:
        """List pending backlog entries."""
        if account_email:
            return list(self.db.execute(
                "SELECT * FROM _sync_backlog WHERE account_email = ? "
                "ORDER BY created_at ASC LIMIT ?",
                (account_email, limit),
            ))
        return list(self.db.execute(
            "SELECT * FROM _sync_backlog ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ))

    # ── Processing ────────────────────────────────────────────────────────

    def process_all(self, account_email: str | None = None) -> int:
        """Process pending backlog entries.

        Acquires a threading lock (timeout 5s).  If another thread is
        already processing, returns 0 immediately.

        Groups entries by account_email and processes in batches.
        Entries that have exceeded ``MAX_RETRIES`` are moved to the
        dead-letter table.

        Args:
            account_email: If set, only process backlog for this account.

        Returns:
            Number of backlog entries successfully processed.
        """
        if not self._lock.acquire(timeout=5):
            logger.warning("[backlog] Lock timeout — another thread is processing")
            return 0
        try:
            return self._process(account_email)
        finally:
            self._lock.release()

    def _process(self, account_email: str | None) -> int:
        """Internal processing — call under lock."""
        if account_email:
            entries = list(self.db.execute(
                "SELECT * FROM _sync_backlog "
                "WHERE account_email = ? "
                "ORDER BY created_at ASC LIMIT ?",
                (account_email, self.BATCH_SIZE),
            ))
        else:
            entries = list(self.db.execute(
                "SELECT * FROM _sync_backlog "
                "ORDER BY created_at ASC LIMIT ?",
                (self.BATCH_SIZE,),
            ))
        if not entries:
            return 0

        # Clean stale entries with NULL imap_uid
        stale = [e for e in entries if e.get("imap_uid") is None]
        if stale:
            logger.warning(
                "[backlog] Deleting %d stale entries with NULL imap_uid", len(stale),
            )
            for e in stale:
                self.db.execute("DELETE FROM _sync_backlog WHERE id = ?", (e["id"],))
            entries = [e for e in entries if e.get("imap_uid") is not None]

        if not entries:
            return 0

        # Group by account
        by_account: dict[str, list[dict]] = defaultdict(list)
        for e in entries:
            by_account[e["account_email"]].append(e)

        synced = 0
        for acct_email, items in by_account.items():
            synced += self._process_account(acct_email, items)
        return synced

    def _process_account(self, account_email: str,
                         items: list[dict]) -> int:
        """Process backlog entries for a single account.

        Dead entries (exceeded MAX_RETRIES) are escalated to the
        dead-letter table before any IMAP connection is attempted.

        Acquires the per-account IMAP lock before connecting to prevent
        concurrent IMAP operations on the same account (e.g. a user-initiated
        sync running at the same time as backlog processing).
        """
        # First: filter out dead entries (regardless of account state)
        live_items: list[dict] = []
        for item in items:
            if item.get("retries", 0) >= self.MAX_RETRIES:
                self._escalate_dead(item, "Exceeded max retries")
            elif item.get("imap_uid") is None:
                self.db.execute("DELETE FROM _sync_backlog WHERE id = ?", (item["id"],))
            else:
                live_items.append(item)

        if not live_items:
            return 0

        # Get account with password
        account_svc = self._get_account_service()
        acct = account_svc.get_account_with_password(account_email)
        if not acct or not acct.get("password"):
            logger.warning(
                "[backlog] No account or password for %s, skipping", account_email,
            )
            # Increment retries for live items
            now = datetime.now(UTC).isoformat()
            for item in live_items:
                self._increment_retry(item, now)
            return 0

        # Acquire per-account IMAP lock to prevent concurrent connections
        from lighterbird.email.service import (
            acquire_account_imap_lock,
            release_account_imap_lock,
        )
        if not acquire_account_imap_lock(account_email):
            logger.warning(
                "[backlog] IMAP lock busy for %s — entries will retry on next pass",
                account_email,
            )
            now = datetime.now(UTC).isoformat()
            for item in live_items:
                self._increment_retry(item, now)
            return 0

        from lighterbird.email.imap.client import IMAPClient

        client = IMAPClient(
            host=acct.get("imap_server", ""),
            port=acct.get("imap_port", 993),
            use_ssl=acct.get("imap_use_ssl", 1) == 1,
        )
        try:
            client.connect(
                username=acct.get("imap_username", "") or account_email,
                password=acct["password"],
            )
            synced = 0
            for item in live_items:
                if self._process_item(client, item, account_email):
                    synced += 1
            return synced
        except Exception:
            logger.warning(
                "[backlog] Connection failure for %s, entries will retry",
                account_email,
            )
            now = datetime.now(UTC).isoformat()
            for item in live_items:
                self._increment_retry(item, now)
            return 0
        finally:
            client.disconnect()
            release_account_imap_lock(account_email)

    def _process_item(self, client: Any, item: dict,
                      account_email: str) -> bool:
        """Process a single backlog entry. Returns True on success.

        Handles three operation types:

        * ``expunge`` — STORE +FLAGS.SILENT (\\Deleted) + EXPUNGE.
          No local DB row update (message already deleted from local DB).
        * ``trash`` — UID MOVE message to Trash folder; fallback to
          COPY + STORE \\Deleted + EXPUNGE.
        * ``sync`` — Set/unset \\Seen and/or \\Deleted flags.

        Note: retry limit check and NULL imap_uid cleanup are handled
        by ``_process_account`` before this is called.
        """
        imap_uid = item.get("imap_uid")
        if imap_uid is None:
            self.db.execute("DELETE FROM _sync_backlog WHERE id = ?", (item["id"],))
            return False

        folder = item.get("folder_name") or "INBOX"
        now = datetime.now(UTC).isoformat()
        operation = item.get("operation", "sync")

        try:
            # ── expunge: permanent deletion from IMAP ─────────────────
            if operation == "expunge":
                ok = client.delete_message_by_uid(folder, str(imap_uid).encode())
                if ok:
                    self.db.execute(
                        "DELETE FROM _sync_backlog WHERE id = ?", (item["id"],),
                    )
                    return True
                # EXPUNGE failed — retry later
                self._increment_retry(item, now)
                return False

            # ── trash: move message to IMAP Trash folder ──────────────
            trash_folder = self._resolve_trash_if_available(account_email)
            if operation == "trash" and folder != trash_folder:
                ok = client.move_message(int(imap_uid), folder, trash_folder)
                if ok:
                    self.db.execute(
                        "UPDATE messages SET folder_name = ?, is_deleted = 0, "
                        "updated_at = ? WHERE uuid = ?",
                        (trash_folder, now, item["msg_uuid"]),
                    )
                    self.db.execute(
                        "DELETE FROM _sync_backlog WHERE id = ?", (item["id"],),
                    )
                    return True
                # Move failed — fall through to flag-only STORE

            # ── sync: set/unset IMAP flags ────────────────────────────
            add: list[str] = []
            remove: list[str] = []
            if item.get("is_read"):
                add.append("\\Seen")
            else:
                remove.append("\\Seen")
            if item.get("is_deleted"):
                add.append("\\Deleted")
            else:
                remove.append("\\Deleted")

            ok = client.set_flags(
                int(imap_uid), folder,
                add=add or None, remove=remove or None,
            )
            if ok:
                self.db.execute(
                    "DELETE FROM _sync_backlog WHERE id = ?", (item["id"],),
                )
                return True

            self._increment_retry(item, now)
            return False
        except Exception:
            logger.warning(
                "[backlog] Item %s (msg %s) failed",
                item.get("id", "?"), item.get("msg_uuid", "")[:8],
            )
            self._increment_retry(item, now)
            return False

    def _increment_retry(self, item: dict, now: str) -> None:
        """Increment retry count and optionally escalate to dead letter."""
        new_retries = item.get("retries", 0) + 1
        if new_retries >= self.MAX_RETRIES:
            self._escalate_dead(item, f"Exceeded max retries ({self.MAX_RETRIES})")
            return
        self.db.execute(
            "UPDATE _sync_backlog SET retries = retries + 1, "
            "last_attempt = ? WHERE id = ?",
            (now, item["id"]),
        )

    def _escalate_dead(self, item: dict, reason: str) -> None:
        """Move backlog entry to dead-letter table."""
        if self._dead_letter:
            self._dead_letter.auto_dead(item, reason)
        else:
            # No dead-letter service configured — just delete
            self.db.execute("DELETE FROM _sync_backlog WHERE id = ?", (item["id"],))

    def _resolve_trash_if_available(self, account_email: str) -> str:
        """Resolve trash folder name if FolderMapper is available."""
        if self._folder_mapper:
            return self._folder_mapper.resolve_trash(account_email)
        return "Trash"

    def _get_account_service(self) -> Any:
        """Get the AccountService singleton."""
        # Lazy import to avoid circular deps at module level
        from lighterbird.email.services.accounts import AccountService

        return AccountService(self.db)


__all__ = ["BacklogLockError", "BacklogOperation", "BacklogService"]
