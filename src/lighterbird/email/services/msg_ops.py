"""Message operations service.

Flat service class, forked from A-lien's RetpostoMessageOpsMixin.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
        if imap_uid is None or not account_email:
            self._enqueue_sync(msg)
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
        entries = list(self.db.execute(
            "SELECT * FROM _sync_backlog ORDER BY created_at ASC LIMIT 500"
        ))
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
    ) -> None:
        """Send an email via SMTP.

        Args:
            account_email: Sender account email.
            to: Primary recipients.
            subject: Email subject.
            body: Message body (markdown, html, or plain text per body_format).
            cc: Carbon-copy recipients.
            bcc: Blind carbon-copy recipients.
            priority: 1 (highest) to 5 (lowest), default 3.
            body_format: "markdown" (default), "html", or "plain".
            attachments: List of base64-encoded attachment content strings.
            signature: Optional override signature. If None, uses account's
                stored signature from the database.
            in_reply_to: Message-ID of the message being replied to, for
                conversation threading (In-Reply-To / References headers).
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
        attachments = attachments or []
        smtp_port = acct.get("smtp_port", 587)

        # Use account's stored signature if no override provided
        if signature is None:
            signature = acct.get("signature", "") or ""

        import uuid as uuid_mod
        message_id = str(uuid_mod.uuid4())

        # Parse body per body_format
        html_body = ""
        final_body = body
        if body_format == "markdown" and body:
            try:
                import mistune
                html_body = mistune.html(body)
                final_body = body  # keep original markdown as plain text fallback
            except ImportError:
                # mistune not installed — fallback to plain text
                html_body = ""
                final_body = body
        elif body_format == "html":
            html_body = body
            final_body = ""  # no plain text fallback for explicit HTML
        # "plain" — final_body stays as-is, no html_body

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
                attachments=attachments,
                signature=signature,
                message_id=message_id,
                in_reply_to=in_reply_to,
            )
        finally:
            client.disconnect()
        # Store sent message locally
        import json as json_mod

        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """INSERT INTO messages
               (uuid, account_email, folder_name, message_id, in_reply_to, from_addr,
                to_recipients, cc_recipients,
                subject, body, is_read, received_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                str(uuid_mod.uuid4()),
                account_email,
                "Sent",
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
