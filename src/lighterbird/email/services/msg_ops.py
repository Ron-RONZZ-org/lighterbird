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

        All local DB updates happen in a single batch for speed.  IMAP
        trash operations are deferred to the background worker.

        Args:
            uuids: List of message UUIDs to trash.

        Returns:
            Dict with ``count`` of successfully trashed messages and
            ``queued`` count for background IMAP sync.
        """
        now = datetime.now(UTC).isoformat()
        queued = 0
        trashed = 0

        for msg_uuid in uuids:
            msg = self.db.execute_one(
                "SELECT * FROM messages WHERE uuid = ? AND is_deleted = 0",
                (msg_uuid,),
            )
            if not msg:
                continue

            # Local soft-delete (instant)
            self.db.execute(
                "UPDATE messages SET is_deleted = 1, updated_at = ? WHERE uuid = ?",
                (now, msg_uuid),
            )
            trashed += 1

            # Queue IMAP trash for background processing
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
                queued += 1

        return {"count": trashed, "queued": queued}

    # ── Hard-delete (permanent) operations ────────────────────────────────
    # Hard delete MUST purge from the remote IMAP server, not just mark
    # locally.  The sync worker compares IMAP UIDs against known_uids in
    # the local DB; if we only soft-delete (is_deleted=1) or delete the
    # row and rely on the async backlog, the next sync re-imports the UID.
    #
    # Strategy: connect to IMAP synchronously, UID STORE +FLAGS (\Deleted)
    # + EXPUNGE (removes the UID from the folder permanently).  If IMAP
    # is unreachable, fall back to keeping the row with is_deleted=1
    # (hidden from list, UID stays in known_uids → no re-import).

    def _imap_delete_uuid(self, msg: dict) -> bool:
        """Synchronously delete a message UID from the IMAP server.

        Connects to IMAP, selects the folder, marks the UID as
        ``\\Deleted``, and EXPUNGEs the folder to permanently remove it.
        Returns ``True`` if the IMAP deletion succeeded, ``False`` if
        the message has no UID or the IMAP operation failed.
        """
        imap_uid = msg.get("imap_uid")
        account_email = msg.get("account_email", "")
        folder_name = msg.get("folder_name", "")
        if imap_uid is None or not account_email or not folder_name:
            return False

        acct = self._account_service.get_account_with_password(account_email)
        if not acct or not acct.get("password"):
            logger.warning("[hard-delete] No password for %s, cannot delete from IMAP", account_email)
            return False

        try:
            from lighterbird.email.imap.client import IMAPClient
            client = IMAPClient(
                host=acct.get("imap_server", ""),
                port=acct.get("imap_port", 993),
                username=account_email,
                password=acct["password"],
                use_ssl=bool(acct.get("imap_use_ssl", 1)),
            )
            client.connect()
            ok = client.delete_message_by_uid(folder_name, str(imap_uid).encode())
            client.disconnect()
            if ok:
                logger.info("[hard-delete] IMAP purge OK for %s UID %s", account_email, imap_uid)
            else:
                logger.warning("[hard-delete] IMAP delete_message_by_uid returned False for %s UID %s", account_email, imap_uid)
            return ok
        except Exception as exc:
            logger.warning(
                "[hard-delete] IMAP connection/delete failed for %s UID %s: %s",
                account_email, imap_uid, exc,
            )
            return False

    def hard_delete_message(self, msg_uuid: str) -> None:
        """Permanently delete a message from the local DB and IMAP server.

        1. Connects to IMAP and performs ``STORE +FLAGS (\\Deleted)``
           + ``EXPUNGE`` to remove the message from the server.
        2. If IMAP succeeds, removes the local DB row permanently.
        3. If IMAP fails, keeps the row with ``is_deleted=1`` so the
           sync worker does not re-import the UID (the UID stays in
           ``known_uids`` and the message stays hidden from the list).
        """
        msg = self.db.execute_one(
            "SELECT * FROM messages WHERE uuid = ?", (msg_uuid,)
        )
        if not msg:
            return

        # Try synchronous IMAP deletion
        imap_ok = self._imap_delete_uuid(msg)
        now = datetime.now(UTC).isoformat()

        if imap_ok:
            # IMAP confirmed deleted — safe to remove local row
            self.db.execute("DELETE FROM messages WHERE uuid = ?", (msg_uuid,))
            logger.info("[hard-delete] Local row deleted for %s", msg_uuid[:8])
        else:
            # IMAP unreachable — keep local row with is_deleted=1 so the
            # message stays hidden from the list and the sync worker does
            # not re-import the UID.
            self.db.execute(
                "UPDATE messages SET is_deleted = 1, updated_at = ? WHERE uuid = ?",
                (now, msg_uuid),
            )
            logger.warning(
                "[hard-delete] IMAP delete failed for %s — kept local row with is_deleted=1",
                msg_uuid[:8],
            )

    def batch_hard_delete_messages(self, uuids: list[str]) -> dict[str, Any]:
        """Permanently delete multiple messages from local DB and IMAP.

        For each message, attempts synchronous IMAP ``STORE +FLAGS (\\Deleted)``
        + ``EXPUNGE``.  Deletes the local row only if IMAP confirms.  Falls
        back to ``is_deleted=1`` if IMAP is unreachable (prevents re-import).

        Returns:
            Dict with ``count`` of locally deleted (hidden) messages.
            ``queued`` is always 0 — hard delete is synchronous.
        """
        now = datetime.now(UTC).isoformat()
        deleted = 0

        for msg_uuid in uuids:
            msg = self.db.execute_one(
                "SELECT * FROM messages WHERE uuid = ?", (msg_uuid,)
            )
            if not msg:
                continue

            # Try synchronous IMAP deletion
            imap_ok = self._imap_delete_uuid(msg)

            if imap_ok:
                self.db.execute("DELETE FROM messages WHERE uuid = ?", (msg_uuid,))
                deleted += 1
            else:
                # Keep row hidden — prevents re-import on next sync
                self.db.execute(
                    "UPDATE messages SET is_deleted = 1, updated_at = ? WHERE uuid = ?",
                    (now, msg_uuid),
                )
                deleted += 1

        return {"count": deleted, "queued": 0}

    def move_message(self, msg_uuid: str, destination_folder_name: str) -> None:
        """Move a message to a different folder (by folder name)."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE messages SET folder_name = ?, updated_at = ? WHERE uuid = ?",
            (destination_folder_name, now, msg_uuid),
        )

    # ── Dead-letter management ────────────────────────────────────────────

    @property
    def dead_letter(self) -> Any:
        """Access the DeadLetterService for manual management."""
        return self.backlog._dead_letter
