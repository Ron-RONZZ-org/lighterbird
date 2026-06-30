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
        """Mark a message as read or unread locally."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE messages SET is_read = ?, updated_at = ? WHERE uuid = ?",
            (1 if is_read else 0, now, msg_uuid),
        )

    def trash_message(self, msg_uuid: str) -> None:
        """Soft-delete a message."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE messages SET is_deleted = 1, updated_at = ? WHERE uuid = ?",
            (now, msg_uuid),
        )

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
        attachments: list[str] | None = None,
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
