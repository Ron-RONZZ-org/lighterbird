"""Message operations service.

Message mutation operations extracted from A-lien's RetpostoMessageOpsMixin.

Send-queue retry with exponential backoff lives in
:mod:`lighterbird.email.services.msg_send`.

Phase 0 of the IMAP sync overhaul: delegates immediate flag sync operations
to :class:`BacklogService` instead of doing inline IMAP STORE calls,
improving UI responsiveness (mark_read no longer blocks on IMAP).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from lighterbird.email.services.backlog import BacklogService
from lighterbird.email.services.dead_letter import DeadLetterService
from lighterbird.email.services.flag_sync import FlagSyncService
from lighterbird.email.services.msg_send import MsgSendQueueMixin

logger = logging.getLogger(__name__)


class MessageOpsService(MsgSendQueueMixin):
    """Message mutation operations (flag sync, trash, move, send).

    Composes :class:`BacklogService` for deferred flag sync and
    :class:`DeadLetterService` for handling entries that exceeded
    retry limits.
    """

    def __init__(self, db, account_service):
        self.db = db
        self._account_service = account_service
        self.backlog = BacklogService(
            db=db,
            pool=None,  # Connection pool added in Phase 4
            folder_mapper=None,  # FolderMapper added in Phase 2
            dead_letter=DeadLetterService(db),
            max_retries=10,
            batch_size=200,
        )
        self.flag_sync = FlagSyncService(
            db=db,
            backlog=self.backlog,
        )

    def mark_read(self, msg_uuid: str, is_read: bool = True) -> None:
        """Mark a message as read or unread locally and queue IMAP sync.

        Local DB update is immediate.  IMAP sync is deferred to the
        backlog for batch processing — no blocking IMAP call.
        """
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE messages SET is_read = ?, updated_at = ? WHERE uuid = ?",
            (1 if is_read else 0, now, msg_uuid),
        )
        self._enqueue_sync(msg_uuid)

    def _enqueue_sync(self, msg_uuid: str) -> None:
        """Queue a message flag sync for background IMAP sync.

        Reads the current message state from DB and enqueues it to the
        backlog.  If the message has no IMAP UID (local-only/seed), it
        is skipped — it will get a real UID when fetched from IMAP.
        """
        msg = self.db.execute_one(
            "SELECT * FROM messages WHERE uuid = ?", (msg_uuid,)
        )
        if not msg:
            return
        imap_uid = msg.get("imap_uid")
        account_email = msg.get("account_email", "")
        if not account_email:
            return
        if imap_uid is None:
            # Local-only message — will get a real UID during fetch
            return
        self.backlog.enqueue(
            msg_uuid=msg_uuid,
            account_email=account_email,
            folder_name=msg.get("folder_name"),
            imap_uid=imap_uid,
            is_read=int(msg.get("is_read", 0)),
            is_deleted=int(msg.get("is_deleted", 0)),
        )

    # ── Backlog processing (delegated) ───────────────────────────────────

    def process_sync_backlog(self) -> int:
        """Process all pending flag sync requests from the backlog.

        Returns:
            Number of backlog entries successfully synced.
        """
        return self.backlog.process_all()

    def process_trash_backlog(self, account_email: str | None = None) -> int:
        """Process pending IMAP trash operations from the backlog.

        Args:
            account_email: If provided, only process for this account.

        Returns:
            Number of entries successfully moved to Trash.
        """
        return self.backlog.process_all(account_email=account_email)

    # ── Trash operations ──────────────────────────────────────────────────

    def trash_message(self, msg_uuid: str) -> None:
        """Move a message to the IMAP server's Trash folder.

        Updates the local DB immediately (soft-delete).  IMAP-level
        move is deferred to the backlog for batch processing.
        """
        now = datetime.now(UTC).isoformat()
        msg = self.db.execute_one(
            "SELECT * FROM messages WHERE uuid = ?", (msg_uuid,)
        )
        if not msg:
            return

        # Local soft-delete first — always instant
        self.db.execute(
            "UPDATE messages SET is_deleted = 1, updated_at = ? WHERE uuid = ?",
            (now, msg_uuid),
        )

        imap_uid = msg.get("imap_uid")
        account_email = msg.get("account_email", "")
        folder_name = msg.get("folder_name", "")

        if imap_uid is not None and account_email and folder_name:
            self.backlog.enqueue_trash(
                msg_uuid=msg_uuid,
                account_email=account_email,
                folder_name=folder_name,
                imap_uid=imap_uid,
            )

    def _enqueue_trash(self, msg: dict) -> None:
        """Legacy method — queue a message for deferred IMAP trash move.

        Provided for backward compatibility with any external callers.
        Delegates to :meth:`BacklogService.enqueue_trash`.
        """
        msg_uuid = msg.get("uuid", "")
        self.backlog.enqueue_trash(
            msg_uuid=msg_uuid,
            account_email=msg.get("account_email", ""),
            folder_name=msg.get("folder_name"),
            imap_uid=msg.get("imap_uid"),
        )

    def batch_trash_messages(self, uuids: list[str]) -> dict[str, Any]:
        """Soft-delete multiple messages locally and queue IMAP trash.

        All local DB updates happen in a single batch inside a transaction
        for speed.  IMAP trash operations are deferred to the background
        worker.

        Args:
            uuids: List of message UUIDs to trash.

        Returns:
            Dict with ``count`` of successfully trashed messages and
            ``queued`` count for background IMAP sync.
        """
        if not uuids:
            return {"count": 0, "queued": 0}

        now = datetime.now(UTC).isoformat()

        # Single SELECT IN to find all non-deleted messages at once
        placeholders = ",".join("?" for _ in uuids)
        existing = {
            row["uuid"]: row for row in self.db.execute(
                f"SELECT * FROM messages WHERE uuid IN ({placeholders}) AND is_deleted = 0",
                tuple(uuids),
            )
        }

        trashed = 0
        backlog_entries: list[tuple] = []

        for msg_uuid in uuids:
            msg = existing.get(msg_uuid)
            if not msg:
                continue
            trashed += 1
            imap_uid = msg.get("imap_uid")
            account_email = msg.get("account_email", "")
            folder_name = msg.get("folder_name", "")
            if imap_uid is not None and account_email and folder_name:
                backlog_entries.append(
                    (msg_uuid, msg_uuid, account_email, folder_name,
                     imap_uid, 1, 1, "trash", now)
                )

        # Single transaction for all mutations
        if trashed:
            with self.db.transaction() as conn:
                conn.execute(
                    f"UPDATE messages SET is_deleted = 1, updated_at = ? "
                    f"WHERE uuid IN ({','.join('?' for _ in uuids)})",
                    (now, *uuids),
                )
                if backlog_entries:
                    conn.executemany(
                        "INSERT OR REPLACE INTO _sync_backlog "
                        "(id, msg_uuid, account_email, folder_name, imap_uid, "
                        " is_read, is_deleted, operation, created_at, "
                        " last_attempt, retries) "
                        "VALUES ("
                        "  COALESCE((SELECT id FROM _sync_backlog "
                        "           WHERE msg_uuid = ?), NULL),"
                        "  ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0"
                        ")",
                        backlog_entries,
                    )

        return {"count": trashed, "queued": len(backlog_entries)}

    # ── Hard-delete (permanent) operations ────────────────────────────────
    #
    # Hard delete removes the local DB row immediately so the UI updates
    # instantly — same UX contract as soft delete (trash_message).
    # The IMAP-level EXPUNGE is deferred to the backlog service for
    # background processing.
    #
    # If the backlog EXPUNGE eventually fails, the message stays on the
    # IMAP server but is invisible in lighterbird (no local row to display).
    # This is acceptable: next UID SEARCH during sync won't re-import the
    # deleted UID because the sync only imports UIDs not already in known_uids,
    # and the deleted row won't be there to block re-import.

    def hard_delete_message(self, msg_uuid: str) -> dict[str, Any]:
        """Permanently delete a message from local DB (instant) and enqueue
        IMAP EXPUNGE for background processing.

        Unlike the old synchronous implementation, this method:
        1. Deletes the local DB row immediately (instant UX).
        2. Enqueues an ``expunge`` backlog entry for background IMAP cleanup.
        3. Returns a status dict immediately — no IMAP round-trip.

        Returns:
            Dict with ``count`` (1 if deleted, 0 if not found), ``queued``
            (1 if IMAP expunge was scheduled, 0 otherwise), and ``errors``
            (empty unless the message was not found).
        """
        msg = self.db.execute_one(
            "SELECT * FROM messages WHERE uuid = ?", (msg_uuid,)
        )
        if not msg:
            return {"count": 0, "queued": 0, "errors": [f"{msg_uuid[:8]}: message not found"]}

        imap_uid = msg.get("imap_uid")
        account_email = msg.get("account_email", "")
        folder_name = msg.get("folder_name", "")

        # Local DB deletion — instant
        self.db.execute("DELETE FROM messages WHERE uuid = ?", (msg_uuid,))

        # Enqueue IMAP EXPUNGE for background processing
        queued = 0
        if imap_uid is not None and account_email and folder_name:
            self.backlog.enqueue_expunge(
                msg_uuid=msg_uuid,
                account_email=account_email,
                folder_name=folder_name,
                imap_uid=imap_uid,
            )
            queued = 1

        return {"count": 1, "queued": queued, "errors": []}

    def batch_hard_delete_messages(self, uuids: list[str]) -> dict[str, Any]:
        """Permanently delete multiple messages from local DB (instant) and
        enqueue IMAP EXPUNGE for background processing.

        All local DB operations happen in a single transaction for speed.
        IMAP EXPUNGE entries are enqueued to the backlog.  The caller gets
        an immediate response with counts.  No IMAP round-trips.

        Returns:
            Dict with ``count`` of locally deleted messages, ``queued``
            count of backlogged expunge operations, and ``errors`` list
            (messages not found are reported as errors).
        """
        if not uuids:
            return {"count": 0, "queued": 0, "errors": []}

        now = datetime.now(UTC).isoformat()

        # Single SELECT IN to find all existing messages at once
        placeholders = ",".join("?" for _ in uuids)
        existing = {
            row["uuid"]: row for row in self.db.execute(
                f"SELECT * FROM messages WHERE uuid IN ({placeholders})",
                tuple(uuids),
            )
        }

        errors: list[str] = []
        to_delete: list[str] = []
        backlog_entries: list[tuple] = []

        for msg_uuid in uuids:
            msg = existing.get(msg_uuid)
            if not msg:
                errors.append(f"{msg_uuid[:8]}: message not found")
                continue
            to_delete.append(msg_uuid)
            imap_uid = msg.get("imap_uid")
            account_email = msg.get("account_email", "")
            folder_name = msg.get("folder_name", "")
            if imap_uid is not None and account_email and folder_name:
                backlog_entries.append(
                    (msg_uuid, msg_uuid, account_email, folder_name,
                     imap_uid, 1, 1, "expunge", now)
                )

        # Single transaction for all mutations
        if to_delete:
            with self.db.transaction() as conn:
                conn.execute(
                    f"DELETE FROM messages WHERE uuid IN "
                    f"({','.join('?' for _ in to_delete)})",
                    tuple(to_delete),
                )
                if backlog_entries:
                    conn.executemany(
                        "INSERT OR REPLACE INTO _sync_backlog "
                        "(id, msg_uuid, account_email, folder_name, imap_uid, "
                        " is_read, is_deleted, operation, created_at, "
                        " last_attempt, retries) "
                        "VALUES ("
                        "  COALESCE((SELECT id FROM _sync_backlog "
                        "           WHERE msg_uuid = ?), NULL),"
                        "  ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0"
                        ")",
                        backlog_entries,
                    )

        return {"count": len(to_delete), "queued": len(backlog_entries), "errors": errors}

    def move_message(self, msg_uuid: str, destination_folder_name: str) -> None:
        """Move a message to a different folder (by folder name)."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE messages SET folder_name = ?, updated_at = ? WHERE uuid = ?",
            (destination_folder_name, now, msg_uuid),
        )

    def batch_move_messages(self, uuids: list[str], destination_folder_name: str) -> int:
        """Move multiple messages to a destination folder in one transaction.

        Args:
            uuids: List of message UUIDs to move.
            destination_folder_name: Target folder name.

        Returns:
            Number of messages moved.
        """
        if not uuids:
            return 0
        now = datetime.now(UTC).isoformat()
        placeholders = ",".join("?" for _ in uuids)
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE messages SET folder_name = ?, updated_at = ? "
                f"WHERE uuid IN ({placeholders})",
                (destination_folder_name, now, *uuids),
            )
        return len(uuids)

    # ── Dead-letter management ────────────────────────────────────────────

    @property
    def dead_letter(self) -> Any:
        """Access the DeadLetterService for manual management."""
        return self.backlog._dead_letter
