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

    def mark_read(self, msg_uuid: str, legita: bool = True) -> None:
        """Mark a message as read or unread locally."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE mesagoj SET legita = ?, modifita_je = ? WHERE uuid = ?",
            (1 if legita else 0, now, msg_uuid),
        )

    def trash_message(self, msg_uuid: str) -> None:
        """Soft-delete a message."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE mesagoj SET forigita = 1, modifita_je = ? WHERE uuid = ?",
            (now, msg_uuid),
        )

    def move_message(self, msg_uuid: str, destination_folder_nomo: str) -> None:
        """Move a message to a different folder (by folder name)."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE mesagoj SET dosierujo_nomo = ?, modifita_je = ? WHERE uuid = ?",
            (destination_folder_nomo, now, msg_uuid),
        )

    def send_email(
        self,
        account_email: str,
        to: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
    ) -> None:
        """Send an email via SMTP."""
        from lighterbird.email.smtp import SMTPClient

        acct = self._account_service.get_account_with_password(account_email)
        if not acct:
            # Check if account exists at all vs just missing password
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
        sender_email = acct.get("retposto", "")
        cc = cc or []
        smtp_port = acct.get("smtp_haveno", 587)

        # Generate Message-ID before sending so it's used both in the SMTP
        # envelope and in the local store — enabling IMAP dedup via Message-ID.
        import uuid as uuid_mod

        message_id = str(uuid_mod.uuid4())

        client = SMTPClient(
            host=acct.get("smtp_servilo", ""),
            port=smtp_port,
            use_tls=acct.get("smtp_tls", 1) == 1,
            use_ssl=smtp_port == 465,
        )
        try:
            client.connect(
                username=acct.get("smtp_uzantonomo", "") or sender_email,
                password=acct["password"],
            )
            client.send_email(
                from_addr=sender_email, to=to, subject=subject,
                body=body, cc=cc, message_id=message_id,
            )
        finally:
            client.disconnect()
        # Store sent message locally with the same Message-ID
        import json as json_mod

        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """INSERT INTO mesagoj
               (uuid, konto_id, dosierujo_nomo, message_id, de, al, kc,
                subjekto, korpo, legita, ricevita_je, kreita_je, modifita_je)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                str(uuid_mod.uuid4()),
                account_email,
                "Sent",
                message_id,
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
