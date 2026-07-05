"""Email send-queue service mixin.

Extracted from :mod:`msg_ops` to keep file sizes under 500 lines.
Provides SMTP send, outbox persistence, and deferred retry with
exponential backoff.

Separated into a mixin class so ``MessageOpsService`` in :mod:`msg_ops`
can inherit and expose all methods through a single public interface.
"""

from __future__ import annotations

import base64
import json as json_mod
import logging
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from typing import Any

from lighterbird.core.backoff import compute_backoff_seconds

logger = logging.getLogger(__name__)


class MsgSendQueueMixin:
    """Mixin providing email send + send-queue retry methods.

    Expects the host class to set::

        self.db          # database connection
        self._account_service  # account lookup with password
    """

    # ── Send email ─────────────────────────────────────────────────────────

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

    # ── Attachment reconstruction ─────────────────────────────────────────

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
