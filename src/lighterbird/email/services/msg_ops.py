"""Message operations service.

Message mutation operations extracted from A-lien's RetpostoMessageOpsMixin.

Send-queue retry with exponential backoff lives in
:mod:`lighterbird.email.services.msg_send`.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from lighterbird.email.services.msg_send import MsgSendQueueMixin

logger = logging.getLogger(__name__)

class MessageOpsService(MsgSendQueueMixin):
    """Message mutation operations (flag sync, trash, move, send)."""

    def __init__(self, db, account_service):
        self.db = db
        self._account_service = account_service

    def mark_read(self, msg_uuid: str, is_read: bool = True) -> None:
        """Mark a message as read or unread locally and sync to IMAP server."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE messages SET is_read = ?, updated_at = ? WHERE uuid = ?",
            (1 if is_read else 0, now, msg_uuid),
        )
        self._imap_sync_flags(msg_uuid)

    def _imap_sync_flags(self, msg_uuid: str) -> None:
        """Sync local message flags to the IMAP server, queuing on failure.

        Reads the current message state from DB and sends STORE commands
        to the IMAP server. Falls back to enqueuing a backlog entry
        if the IMAP connection fails.
        """
        msg = self.db.execute_one(
            "SELECT * FROM messages WHERE uuid = ?", (msg_uuid,)
        )
        if not msg:
            return
        account_email = msg.get("account_email", "")
        imap_uid = msg.get("imap_uid")
        if not account_email:
            return  # No account — nothing to sync to
        if imap_uid is None:
            # No IMAP UID (e.g., local-only seeded message or draft).
            # The message will get a real UID when it's fetched from the
            # IMAP server during sync. Until then, there's no point
            # enqueuing — process_sync_backlog can't process a NULL UID.
            return
        folder_name = msg.get("folder_name", "")
        acct = self._account_service.get_account_with_password(account_email)
        if not acct or not acct.get("password"):
            self._enqueue_sync(msg)
            return

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
            add: list[str] = []
            remove: list[str] = []
            if msg.get("is_read"):
                add.append("\\Seen")
            else:
                remove.append("\\Seen")
            if msg.get("is_deleted"):
                add.append("\\Deleted")
            else:
                remove.append("\\Deleted")
            ok = client.set_flags(
                int(imap_uid), folder_name or "INBOX",
                add=add or None, remove=remove or None,
            )
            if not ok:
                raise RuntimeError(
                    f"Failed to set flags for UID {imap_uid} in folder {folder_name}"
                )
        except Exception:
            self._enqueue_sync(msg)
        finally:
            client.disconnect()

    def _enqueue_sync(self, msg: dict) -> None:
        """Queue a message flag sync request for later processing."""
        now = datetime.now(timezone.utc).isoformat()
        msg_uuid = msg.get("uuid", "")
        self.db.execute(
            "INSERT OR REPLACE INTO _sync_backlog "
            "(id, msg_uuid, account_email, folder_name, imap_uid, "
            " is_read, is_deleted, created_at, last_attempt, retries) "
            "VALUES ("
            "  COALESCE((SELECT id FROM _sync_backlog WHERE msg_uuid = ?), NULL),"
            "  ?, ?, ?, ?, ?, ?, ?, NULL, 0"
            ")",
            (msg_uuid, msg_uuid, msg.get("account_email", ""),
             msg.get("folder_name", ""),
             msg.get("imap_uid"),
             int(msg.get("is_read", 0)),
             int(msg.get("is_deleted", 0)), now),
        )

    def process_sync_backlog(self) -> int:
        """Process all pending flag sync requests.

        Connects to each account's IMAP server and sends STORE commands
        for queued flag changes. Clears successfully synced entries.

        Returns:
            Number of backlog entries successfully synced.
        """
        import logging
        logger = logging.getLogger(__name__)

        entries = list(self.db.execute(
            "SELECT * FROM _sync_backlog ORDER BY created_at ASC LIMIT 500"
        ))
        if not entries:
            return 0

        # Clean up stale entries with NULL imap_uid (created by older code
        # for seeded/local-only messages that can never be synced to IMAP).
        stale = [e for e in entries if e.get("imap_uid") is None]
        if stale:
            logger.warning(
                "Deleting %d stale backlog entries with NULL imap_uid",
                len(stale),
            )
            for e in stale:
                self.db.execute(
                    "DELETE FROM _sync_backlog WHERE id = ?", (e["id"],)
                )
            entries = [e for e in entries if e.get("imap_uid") is not None]

        if not entries:
            return 0

        from collections import defaultdict
        by_account: dict[str, list[dict]] = defaultdict(list)
        for e in entries:
            by_account[e["account_email"]].append(e)
        synced = 0
        for account_email, items in by_account.items():
            acct = self._account_service.get_account_with_password(account_email)
            if not acct or not acct.get("password"):
                continue
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
                for item in items:
                    try:
                        imap_uid = item.get("imap_uid")
                        if imap_uid is None:
                            continue
                        folder = item.get("folder_name") or "INBOX"
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
                        if not ok:
                            raise RuntimeError(
                                f"Failed to set flags for UID {imap_uid} in folder {folder}"
                            )
                        self.db.execute(
                            "DELETE FROM _sync_backlog WHERE id = ?",
                            (item["id"],),
                        )
                        synced += 1
                    except Exception:
                        self.db.execute(
                            "UPDATE _sync_backlog SET retries = retries + 1, "
                            "last_attempt = ? WHERE id = ?",
                            (datetime.now(timezone.utc).isoformat(), item["id"]),
                        )
            except Exception:
                pass
            finally:
                client.disconnect()
        return synced

    def trash_message(self, msg_uuid: str) -> None:
        """Move a message to the IMAP server's Trash folder.
        
        Updates the local DB immediately (soft-delete). Then attempts
        an IMAP-level move; if that fails, the message is queued for
        background retry during the next sync.
        """
        now = datetime.now(timezone.utc).isoformat()
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

        # Attempt IMAP-level move to Trash (best-effort)
        imap_uid = msg.get("imap_uid")
        account_email = msg.get("account_email", "")
        folder_name = msg.get("folder_name", "")

        if imap_uid is not None and account_email and folder_name:
            try:
                from lighterbird.email.imap.client import IMAPClient
                acct = self._account_service.get_account_with_password(account_email)
                if acct and acct.get("password"):
                    client = IMAPClient(
                        host=acct.get("imap_server", ""),
                        port=acct.get("imap_port", 993),
                        use_ssl=acct.get("imap_use_ssl", 1) == 1,
                    )
                    client.connect(
                        username=acct.get("imap_username", "") or account_email,
                        password=acct["password"],
                    )
                    try:
                        ok = client.move_message(imap_uid, folder_name, "Trash")
                        if ok:
                            self.db.execute(
                                "UPDATE messages SET folder_name = 'Trash', "
                                "is_deleted = 0, updated_at = ? WHERE uuid = ?",
                                (now, msg_uuid),
                            )
                            return  # Success — no need to queue
                    finally:
                        client.disconnect()
            except Exception:
                pass  # Fall through to queue for background retry

        # Queue for background IMAP trash retry
        self._enqueue_trash(msg)

    def _enqueue_trash(self, msg: dict) -> None:
        """Queue a message for deferred IMAP trash move.

        The trash_backlog table stores pending IMAP trash operations
        that are processed in bulk per account by the background worker.
        """
        now = datetime.now(timezone.utc).isoformat()
        msg_uuid = msg.get("uuid", "")
        self.db.execute(
            "INSERT OR REPLACE INTO _sync_backlog "
            "(id, msg_uuid, account_email, folder_name, imap_uid, "
            " is_read, is_deleted, created_at, last_attempt, retries) "
            "VALUES ("
            "  COALESCE((SELECT id FROM _sync_backlog WHERE msg_uuid = ?), NULL),"
            "  ?, ?, ?, ?, ?, ?, ?, NULL, 0"
            ")",
            (msg_uuid, msg_uuid, msg.get("account_email", ""),
             msg.get("folder_name", ""),
             msg.get("imap_uid"),
             1, 1, now),  # is_read=1, is_deleted=1 → Flags to sync: \\Seen + \\Deleted
        )

    def batch_trash_messages(self, uuids: list[str]) -> dict[str, Any]:
        """Soft-delete multiple messages locally and queue IMAP trash.

        All local DB updates happen in a single batch for speed. IMAP
        trash operations are deferred to the background worker.

        Args:
            uuids: List of message UUIDs to trash.

        Returns:
            Dict with ``count`` of successfully trashed messages and
            ``queued`` count for background IMAP sync.
        """
        now = datetime.now(timezone.utc).isoformat()
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
                self.db.execute(
                    "INSERT OR REPLACE INTO _sync_backlog "
                    "(id, msg_uuid, account_email, folder_name, imap_uid, "
                    " is_read, is_deleted, created_at, last_attempt, retries) "
                    "VALUES ("
                    "  COALESCE((SELECT id FROM _sync_backlog WHERE msg_uuid = ?), NULL),"
                    "  ?, ?, ?, ?, ?, ?, ?, NULL, 0"
                    ")",
                    (msg_uuid, msg_uuid, account_email, folder_name,
                     imap_uid, 1, 1, now),
                )
                queued += 1

        return {"count": trashed, "queued": queued}

    def process_trash_backlog(self, account_email: str | None = None) -> int:
        """Process pending IMAP trash operations from the backlog.

        Groups queued entries by account, opens one IMAP connection per
        account, and attempts IMAP MOVE to Trash for each. Successfully
        moved entries are updated in the local DB (folder='Trash',
        is_deleted=0) and removed from the backlog.

        Args:
            account_email: If provided, only process trash backlog for
                           this specific account. Otherwise process for all.

        Returns:
            Number of backlog entries successfully moved to Trash.
        """
        if account_email:
            entries = list(self.db.execute(
                "SELECT * FROM _sync_backlog WHERE is_deleted = 1 "
                "AND account_email = ? ORDER BY created_at ASC LIMIT 500",
                (account_email,),
            ))
        else:
            entries = list(self.db.execute(
                "SELECT * FROM _sync_backlog WHERE is_deleted = 1 "
                "ORDER BY created_at ASC LIMIT 500"
            ))
        if not entries:
            return 0

        from collections import defaultdict
        by_account: dict[str, list[dict]] = defaultdict(list)
        for e in entries:
            by_account[e["account_email"]].append(e)

        moved = 0
        now = datetime.now(timezone.utc).isoformat()
        for account_email, items in by_account.items():
            acct = self._account_service.get_account_with_password(account_email)
            if not acct or not acct.get("password"):
                continue

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
                for item in items:
                    try:
                        imap_uid = item.get("imap_uid")
                        folder = item.get("folder_name") or "INBOX"
                        if imap_uid is None:
                            continue
                        ok = client.move_message(int(imap_uid), folder, "Trash")
                        if ok:
                            msg_uuid = item["msg_uuid"]
                            self.db.execute(
                                "UPDATE messages SET folder_name = 'Trash', "
                                "is_deleted = 0, updated_at = ? WHERE uuid = ?",
                                (now, msg_uuid),
                            )
                            self.db.execute(
                                "DELETE FROM _sync_backlog WHERE id = ?",
                                (item["id"],),
                            )
                            moved += 1
                        else:
                            self.db.execute(
                                "UPDATE _sync_backlog SET retries = retries + 1, "
                                "last_attempt = ? WHERE id = ?",
                                (now, item["id"]),
                            )
                    except Exception:
                        self.db.execute(
                            "UPDATE _sync_backlog SET retries = retries + 1, "
                            "last_attempt = ? WHERE id = ?",
                            (now, item["id"]),
                        )
            except Exception:
                pass  # Account-wide failure — all items stay queued
            finally:
                client.disconnect()
        return moved

    def move_message(self, msg_uuid: str, destination_folder_name: str) -> None:
        """Move a message to a different folder (by folder name)."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE messages SET folder_name = ?, updated_at = ? WHERE uuid = ?",
            (destination_folder_name, now, msg_uuid),
        )
