"""Message operations service.

Flat service class, forked from A-lien's RetpostoMessageOpsMixin.

Includes outbox/send-queue retry with exponential backoff for email
and calendar operations where the remote server is unreachable.
"""

from __future__ import annotations

import base64
import json as json_mod
import logging
import uuid as uuid_mod
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from lighterbird.core.backoff import compute_backoff_seconds

logger = logging.getLogger(__name__)

class MessageOpsService:
    """Message mutation operations."""

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

    def process_trash_backlog(self) -> int:
        """Process pending IMAP trash operations from the backlog.

        Groups queued entries by account, opens one IMAP connection per
        account, and attempts IMAP MOVE to Trash for each. Successfully
        moved entries are updated in the local DB (folder='Trash',
        is_deleted=0) and removed from the backlog.

        Returns:
            Number of backlog entries successfully moved to Trash.
        """
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

    def send_email(
        self,
        account_email: str,
        to: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        priority: int = 3,
        body_format: str = "markdown",
        attachments: list[dict[str, Any]] | None = None,
        signature: str | None = None,
        in_reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send an email via SMTP with outbox fallback on connection failure.

        Always saves the composed message to the local database first
        (folder = ``"Outbox"``). Then attempts SMTP delivery:

        * **On success**: moves the message to the ``"Sent"`` folder.
        * **On connection failure**: leaves the message in ``"Outbox"``
          and enqueues a retry with exponential backoff via
          :meth:`process_send_queue`.

        Args:
            account_email: Sender account email.
            to: Primary recipients.
            subject: Email subject.
            body: Message body (markdown, html, or plain text per body_format).
            cc: Carbon-copy recipients.
            bcc: Blind carbon-copy recipients.
            priority: 1 (highest) to 5 (lowest), default 3.
            body_format: "markdown" (default), "html", or "plain".
            attachments: List of dicts with ``name`` and ``data`` (base64).
            signature: Optional override signature. If None, uses account's
                stored signature from the database.
            in_reply_to: Message-ID of the message being replied to, for
                conversation threading (In-Reply-To / References headers).

        Returns:
            Dict with ``status`` ("sent" or "queued"), ``uuid`` (message UUID),
            and ``message_id`` (SMTP Message-ID).
        """
        from lighterbird.email.smtp import SMTPClient

        acct = self._account_service.get_account_with_password(account_email)
        if not acct:
            exists = self._account_service.get(account_email)
            if not exists:
                raise ValueError(
                    f"Account '{account_email}' not found. "
                    f"Use !email account list to see available accounts."
                )
            raise ValueError(
                f"No password configured for account {account_email}. "
                f"Set it with: !email account modify {account_email} --password <pw>"
            )
        sender_email = acct.get("email", "")
        cc = cc or []
        bcc = bcc or []
        att_list = attachments or []
        smtp_port = acct.get("smtp_port", 587)

        # Use account's stored signature if no override provided
        if signature is None:
            signature = acct.get("signature", "") or ""

        msg_uuid = str(uuid_mod.uuid4())
        message_id = str(uuid_mod.uuid4())

        # Parse body per body_format
        html_body = ""
        final_body = body
        if body_format == "markdown" and body:
            try:
                import mistune
                html_body = mistune.html(body)
                final_body = body
            except ImportError:
                html_body = ""
                final_body = body
        elif body_format == "html":
            html_body = body
            final_body = ""
        # "plain" — final_body stays as-is, no html_body

        # Step 1: Save to Outbox folder first (never lose the message)
        self._ensure_folder(account_email, "Outbox")
        self._save_outbox_message(
            msg_uuid=msg_uuid,
            account_email=account_email,
            sender_email=sender_email,
            to=to,
            cc=cc,
            subject=subject,
            body=body,
            body_format=body_format,
            message_id=message_id,
            in_reply_to=in_reply_to,
            attachments=att_list,
        )

        # Step 2: Attempt SMTP send
        send_error: str | None = None
        client = SMTPClient(
            host=acct.get("smtp_server", ""),
            port=smtp_port,
            use_tls=acct.get("smtp_use_tls", 1) == 1,
            use_ssl=smtp_port == 465,
        )
        try:
            client.connect(
                username=acct.get("smtp_username", "") or sender_email,
                password=acct["password"],
            )
            client.send_email(
                from_addr=sender_email, to=to, subject=subject,
                body=final_body, cc=cc, bcc=bcc,
                html_body=html_body,
                attachments=att_list,
                signature=signature,
                message_id=message_id,
                in_reply_to=in_reply_to,
            )
        except ConnectionError as e:
            send_error = str(e)
        except Exception as e:
            send_error = str(e)
        finally:
            client.disconnect()

        # Step 3: On success → Sent; on failure → queue for retry
        now = datetime.now(timezone.utc).isoformat()
        if send_error is None:
            self.db.execute(
                "UPDATE messages SET folder_name = 'Sent', is_read = 1, "
                "updated_at = ? WHERE uuid = ?",
                (now, msg_uuid),
            )
            logger.info("Email %s sent successfully to %s", msg_uuid[:8], to)
            return {"status": "sent", "uuid": msg_uuid, "message_id": message_id}
        else:
            self._enqueue_send(msg_uuid, account_email, body_format, signature,
                               priority, send_error)
            logger.warning(
                "Email %s queued for retry (SMTP failed: %s)", msg_uuid[:8], send_error,
            )
            return {"status": "queued", "uuid": msg_uuid, "message_id": message_id,
                    "error": send_error}

    # ── Outbox / send-queue helpers ───────────────────────────────────────

    def _ensure_folder(self, account_email: str, folder_name: str) -> None:
        """Create a folder if it does not exist for the given account."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT OR IGNORE INTO folders (account_email, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (account_email, folder_name, now, now),
        )

    def _save_outbox_message(
        self,
        msg_uuid: str,
        account_email: str,
        sender_email: str,
        to: list[str],
        cc: list[str],
        subject: str,
        body: str,
        body_format: str,
        message_id: str,
        in_reply_to: str | None,
        attachments: list[dict[str, Any]],
    ) -> None:
        """Insert a message record into the Outbox folder and persist attachments."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """INSERT INTO messages
               (uuid, account_email, folder_name, message_id, in_reply_to, from_addr,
                to_recipients, cc_recipients, subject, body, is_read,
                received_at, created_at, updated_at)
               VALUES (?, ?, 'Outbox', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (
                msg_uuid,
                account_email,
                message_id,
                in_reply_to or "",
                sender_email,
                json_mod.dumps(to),
                json_mod.dumps(cc),
                subject,
                body,
                now,
                now,
                now,
            ),
        )

        # Store attachments via AttachmentStore so they survive process restart
        if not attachments:
            return
        from lighterbird.core.storage import AttachmentStore
        store = AttachmentStore()
        for att in attachments:
            if not isinstance(att, dict):
                continue
            name = att.get("name", "attachment")
            data_b64 = att.get("data", "")
            try:
                raw = base64.b64decode(data_b64) if data_b64 else b""
            except Exception:
                raw = data_b64.encode("utf-8") if isinstance(data_b64, str) else b""
            if not raw:
                continue
            content_id = str(uuid_mod.uuid4())
            store.store(msg_uuid, content_id, raw)
            self.db.execute(
                """INSERT INTO email_attachments
                   (uuid, message_uuid, filename, mime_type, size, content_id,
                    storage_path, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid_mod.uuid4()),
                    msg_uuid,
                    name,
                    "application/octet-stream",
                    len(raw),
                    content_id,
                    str(store._message_dir(msg_uuid) / content_id),
                    now,
                    now,
                ),
            )

    def _enqueue_send(
        self,
        msg_uuid: str,
        account_email: str,
        body_format: str,
        signature: str,
        priority: int,
        error: str,
    ) -> None:
        """Insert a send-queue entry for deferred retry."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """INSERT OR REPLACE INTO send_queue
               (id, msg_uuid, account_email, body_format, signature, priority,
                status, retries, max_retries, next_attempt, last_error,
                created_at, updated_at)
               VALUES (
                 COALESCE((SELECT id FROM send_queue WHERE msg_uuid = ?), NULL),
                 ?, ?, ?, ?, ?, 'pending', 0, 10, ?, ?, ?, ?
               )""",
            (
                msg_uuid,
                msg_uuid,
                account_email,
                body_format,
                signature,
                priority,
                None,  # next_attempt = immediate (NULL = retry ASAP)
                error,
                now,
                now,
            ),
        )

    def _mark_sent(self, msg_uuid: str) -> None:
        """Move a message from Outbox to Sent and remove its send-queue entry."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE messages SET folder_name = 'Sent', is_read = 1, updated_at = ? WHERE uuid = ?",
            (now, msg_uuid),
        )
        self.db.execute("DELETE FROM send_queue WHERE msg_uuid = ?", (msg_uuid,))

    def _mark_failed(self, msg_uuid: str, error: str) -> None:
        """Move a message from Outbox to Failed and update the send-queue entry."""
        row = self.db.execute_one(
            "SELECT account_email FROM messages WHERE uuid = ?", (msg_uuid,)
        )
        if row:
            self._ensure_folder(row["account_email"], "Failed")
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE messages SET folder_name = 'Failed', updated_at = ? WHERE uuid = ?",
            (now, msg_uuid),
        )
        self.db.execute(
            "UPDATE send_queue SET status = 'failed', last_error = ?, updated_at = ? WHERE msg_uuid = ?",
            (error, now, msg_uuid),
        )

    def _reconstruct_attachments(self, msg_uuid: str) -> list[dict[str, Any]]:
        """Reconstruct attachment dicts from stored data for SMTPClient.

        Args:
            msg_uuid: The message UUID whose attachments to reconstruct.

        Returns:
            List of ``{"name": ..., "data": base64}`` dicts suitable for
            :meth:`SMTPClient.send_email`.
        """
        from lighterbird.core.storage import AttachmentStore

        rows = list(self.db.execute(
            "SELECT filename, content_id FROM email_attachments WHERE message_uuid = ?",
            (msg_uuid,),
        ))
        if not rows:
            return []
        store = AttachmentStore()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                raw = store.retrieve(msg_uuid, row["content_id"])
                data_b64 = base64.b64encode(raw).decode("ascii")
                result.append({"name": row["filename"], "data": data_b64})
            except FileNotFoundError:
                logger.warning(
                    "Attachment %s missing for message %s",
                    row["content_id"][:12], msg_uuid[:8],
                )
                continue
        return result

    # ── Send-queue processing ─────────────────────────────────────────────

    def process_send_queue(self, limit: int = 50) -> dict[str, Any]:
        """Process pending send-queue entries with exponential backoff.

        Retries messages in the ``send_queue`` where:
        * ``status = 'pending'`` and ``next_attempt IS NULL`` or
          ``next_attempt <= now``
        * ``retries < max_retries``

        On success: message moves to ``"Sent"`` and queue entry is removed.
        On failure: ``retries`` is incremented, ``next_attempt`` is set
        with exponential backoff, and status stays ``'pending'``.
        After ``max_retries`` exhausted: status becomes ``'failed'``
        and message moves to ``"Failed"`` folder.

        Args:
            limit: Maximum number of queue entries to process this call.

        Returns:
            Dict with ``sent``, ``retrying``, ``failed`` counts and
            ``errors`` list.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        entries = list(self.db.execute(
            """SELECT sq.*, m.subject, m.to_recipients, m.cc_recipients,
                      m.from_addr, m.body
               FROM send_queue sq
               JOIN messages m ON m.uuid = sq.msg_uuid
               WHERE sq.status = 'pending'
                 AND sq.retries < sq.max_retries
                 AND (sq.next_attempt IS NULL OR sq.next_attempt <= ?)
               ORDER BY sq.created_at ASC
               LIMIT ?""",
            (now_iso, limit),
        ))
        if not entries:
            return {"sent": 0, "retrying": 0, "failed": 0, "errors": []}

        from datetime import timedelta
        from lighterbird.email.smtp import SMTPClient

        sent = 0
        retrying = 0
        failed = 0
        errors: list[str] = []

        for entry in entries:
            msg_uuid = entry["msg_uuid"]
            account_email = entry["account_email"]
            body_format = entry.get("body_format", "markdown")
            signature = entry.get("signature", "") or ""
            priority = entry.get("priority", 3)
            retries = entry.get("retries", 0)
            max_retries = entry.get("max_retries", 10)

            # Parse recipients from JSON
            try:
                to = json_mod.loads(entry.get("to_recipients", "[]"))
            except (json_mod.JSONDecodeError, TypeError):
                to = []
            try:
                cc = json_mod.loads(entry.get("cc_recipients", "[]"))
            except (json_mod.JSONDecodeError, TypeError):
                cc = []
            subject = entry.get("subject", "")
            body_text = entry.get("body", "")
            sender_email = entry.get("from_addr", "")

            acct = self._account_service.get_account_with_password(account_email)
            if not acct or not acct.get("password"):
                self.db.execute(
                    "UPDATE send_queue SET status = 'failed', last_error = ?, "
                    "updated_at = ? WHERE msg_uuid = ?",
                    ("Account not found or no password", now_iso, msg_uuid),
                )
                failed += 1
                errors.append(f"{msg_uuid[:8]}: account not found/no password")
                continue

            smtp_port = acct.get("smtp_port", 587)

            # Mark as running
            self.db.execute(
                "UPDATE send_queue SET status = 'running', updated_at = ? WHERE msg_uuid = ?",
                (now_iso, msg_uuid),
            )

            # Parse body per body_format
            html_body = ""
            final_body = body_text
            if body_format == "markdown" and body_text:
                try:
                    import mistune
                    html_body = mistune.html(body_text)
                    final_body = body_text
                except ImportError:
                    html_body = ""
                    final_body = body_text
            elif body_format == "html":
                html_body = body_text
                final_body = ""

            # Reconstruct attachments
            attachments = self._reconstruct_attachments(msg_uuid)

            # Attempt SMTP send
            smtp_error: str | None = None
            client = SMTPClient(
                host=acct.get("smtp_server", ""),
                port=smtp_port,
                use_tls=acct.get("smtp_use_tls", 1) == 1,
                use_ssl=smtp_port == 465,
            )
            try:
                client.connect(
                    username=acct.get("smtp_username", "") or sender_email,
                    password=acct["password"],
                )
                client.send_email(
                    from_addr=sender_email, to=to, subject=subject,
                    body=final_body, cc=cc,
                    html_body=html_body,
                    attachments=attachments,
                    signature=signature,
                )
            except ConnectionError as e:
                smtp_error = str(e)
            except Exception as e:
                smtp_error = str(e)
            finally:
                client.disconnect()

            if smtp_error is None:
                # Success
                self._mark_sent(msg_uuid)
                sent += 1
                logger.info(
                    "Send-queue: %s sent successfully (after %d retries)",
                    msg_uuid[:8], retries,
                )
            else:
                new_retries = retries + 1
                if new_retries >= max_retries:
                    # Exhausted — mark permanently failed
                    err_msg = (
                        f"Max retries ({max_retries}) reached. "
                        f"Last error: {smtp_error}"
                    )
                    self._mark_failed(msg_uuid, err_msg)
                    failed += 1
                    errors.append(f"{msg_uuid[:8]}: {err_msg}")
                    logger.warning(
                        "Send-queue: %s failed permanently: %s",
                        msg_uuid[:8], err_msg,
                    )
                else:
                    # Schedule next attempt with exponential backoff
                    delay = compute_backoff_seconds(new_retries - 1)
                    next_attempt_dt = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    next_attempt_str = next_attempt_dt.isoformat()
                    self.db.execute(
                        """UPDATE send_queue
                           SET status = 'pending', retries = ?, next_attempt = ?,
                               last_error = ?, updated_at = ?
                           WHERE msg_uuid = ?""",
                        (new_retries, next_attempt_str, smtp_error, now_iso, msg_uuid),
                    )
                    retrying += 1
                    logger.info(
                        "Send-queue: %s retry %d/%d in %ds: %s",
                        msg_uuid[:8], new_retries, max_retries, delay, smtp_error,
                    )

        return {
            "sent": sent,
            "retrying": retrying,
            "failed": failed,
            "errors": errors,
        }
