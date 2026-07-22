"""Email send-queue management with exponential backoff.

Provides the ``MsgQueueMixin`` with methods for enqueuing deferred sends,
processing the send queue with retry via exponential backoff, and updating
message status (sent/failed).

Methods defined here expect to be mixed into a class that sets::

    self.db               # database connection
    self._account_service  # account lookup with password
"""

from __future__ import annotations

import json as json_mod
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from lighterbird.core.backoff import compute_backoff_seconds

logger = logging.getLogger(__name__)


class MsgQueueMixin:
    """Mixin for email send-queue management with exponential backoff.

    Expects the host class to set ``self.db`` and ``self._account_service``.
    Methods ``_reconstruct_attachments()`` and ``_ensure_folder()`` are
    expected via MRO from the host class.
    """

    def _enqueue_send(
        self,
        msg_uuid: str,
        account_email: str,
        body_format: str,
        signature: str,
        priority: int,
        error: str,
        signature_format: str = "plain",
    ) -> None:
        """Insert a send-queue entry for deferred retry."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            """INSERT OR REPLACE INTO send_queue
               (id, msg_uuid, account_email, body_format, signature,
                signature_format, priority,
                status, retries, max_retries, next_attempt, last_error,
                created_at, updated_at)
               VALUES (
                 COALESCE((SELECT id FROM send_queue WHERE msg_uuid = ?), NULL),
                 ?, ?, ?, ?, ?, ?, 'pending', 0, 10, ?, ?, ?, ?
               )""",
            (
                msg_uuid,
                msg_uuid,
                account_email,
                body_format,
                signature,
                signature_format,
                priority,
                None,  # next_attempt = immediate (NULL = retry ASAP)
                error,
                now,
                now,
            ),
        )

    def _mark_sent(self, msg_uuid: str) -> None:
        """Move a message from Outbox to Sent and remove its send-queue entry."""
        now = datetime.now(UTC).isoformat()
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
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE messages SET folder_name = 'Failed', updated_at = ? WHERE uuid = ?",
            (now, msg_uuid),
        )
        self.db.execute(
            "UPDATE send_queue SET status = 'failed', last_error = ?, updated_at = ? WHERE msg_uuid = ?",
            (error, now, msg_uuid),
        )

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
        now_iso = datetime.now(UTC).isoformat()
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
            signature_format = entry.get("signature_format", "plain")
            entry.get("priority", 3)
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
                from lighterbird.server.render_utils import convert_to_html

                html_body = convert_to_html(body_text, "markdown")
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
                    signature_format=signature_format,
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
                    next_attempt_dt = datetime.now(UTC) + timedelta(seconds=delay)
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


__all__ = ["MsgQueueMixin"]
