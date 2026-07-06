"""EmailService — unified facade for email operations.

Composes AccountService, MessageService, and MessageOpsService.
"""

from __future__ import annotations

import email.parser
from pathlib import Path
from typing import Any

from lighterbird.core.drafts import save_draft
from lighterbird.email.db import get_db
from lighterbird.email.services import (
    AccountService,
    MessageOpsService,
    MessageService,
    SieveService,
)


class EmailService:
    """Unified email operations facade."""

    def __init__(self, db=None):
        self._db = db or get_db()
        self.accounts = AccountService(self._db)
        self.messages = MessageService(self._db)
        self.msg_ops = MessageOpsService(self._db, self.accounts)
        self.sieve = SieveService(self._db)

    # ── Account operations ───────────────────────────────────────────────

    def create_account(self, data: dict, password: str) -> dict:
        return self.accounts.create_account(data, password)

    def list_accounts(self):
        return self.accounts.list_accounts()

    def delete_account(self, email: str):
        """Delete an account and its keyring password.

        DB deletion first (cascades to messages, attachments), then
        keyring — prevents password orphan if DB fails.
        Follows pattern from A-lien's ``RetpostoAccountsMixin.delete_account``.
        """
        result = self.accounts.delete(email)
        if result:
            self.accounts.delete_password(email)
        return result

    def get_account(self, email: str):
        return self.accounts.get_account_with_password(email)

    def resolve_account(self, identifier: str):
        return self.accounts.resolve_account(identifier)

    # ── Sync ─────────────────────────────────────────────────────────────

    def sync_account(self, email: str, force: bool = False):
        """Sync messages for a single account by email.

        Always returns a SyncResult (never raises). Pending flag syncs
        (\\Seen, \\Deleted) from the backlog are processed regardless
        of whether the IMAP fetch succeeds.
        """
        from lighterbird.email.imap import sync_account as _sync
        from lighterbird.email.imap.sync import SyncResult

        result = SyncResult()
        acct = self.accounts.get_account_with_password(email)
        if not acct:
            result.errors.append(f"Account not found: {email}")
        elif not acct.get("password"):
            result.errors.append(
                f"No password configured for account {email}. "
                f"Set it with: !email account modify {email} --password <pw>"
            )
        else:
            try:
                result = _sync(
                    host=acct.get("imap_server", ""),
                    port=acct.get("imap_port", 993),
                    use_ssl=acct.get("imap_use_ssl", 1) == 1,
                    username=acct.get("imap_username", "") or acct.get("email", ""),
                    password=acct["password"],
                    account_email=email,
                    db_store=self,
                    force=force,
                )
            except ConnectionError as e:
                result = SyncResult()
                result.errors.append(str(e))
            except Exception as e:
                result = SyncResult()
                result.errors.append(f"Sync error: {e}")
        # ALWAYS drain the flag sync backlog, even on sync failure.
        # This ensures \\Seen and \\Deleted flags pushed by mark_read
        # and trash_message are eventually sent to the IMAP server.
        backlog = self.msg_ops.process_sync_backlog()
        if backlog:
            result.total += backlog
        return result

    def sync_all(self, force: bool = False) -> dict[str, dict]:
        """Sync messages for all accounts."""
        results = {}
        for acct in self.accounts.list_accounts():
            email = acct["email"]
            try:
                sr = self.sync_account(email, force=force)
                results[email] = sr.to_dict()
            except Exception as e:
                results[email] = {"total": 0, "new": 0, "errors": [str(e)]}
        return results

    # ── Message queries ──────────────────────────────────────────────────

    def get_message(self, uuid_: str):
        return self.messages.get_message(uuid_)

    def list_messages(self, account_email=None, folder=None, limit=50, offset=0, sort="newest"):
        return self.messages.list_messages(
            account_email=account_email, folder=folder, limit=limit, offset=offset, sort=sort
        )

    def search_messages(self, filters: dict, limit=50):
        return self.messages.search_messages(filters, limit=limit)

    def export_eml(self, uuid_: str) -> str | None:
        """Export a message as .eml (RFC 822) string."""
        return self.messages.export_eml(uuid_)

    def import_eml(self, path: str) -> dict[str, Any]:
        """Import a .eml file and save it as an email draft.

        Returns the created draft dict.
        """
        eml_path = Path(path)
        if not eml_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(eml_path, "rb") as f:
            parsed = email.parser.BytesParser().parse(f)

        subject = parsed.get("Subject", "(imported)")
        from_addr = parsed.get("From", "")
        to_addr = parsed.get("To", "")
        body = ""
        if parsed.is_multipart():
            for part in parsed.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
                    break
        else:
            payload = parsed.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")

        draft_data = {
            "subject": subject,
            "from_addr": from_addr,
            "to_addr": to_addr,
            "body": body,
        }
        draft = save_draft(domain="email", title=subject, data=draft_data)
        return draft

    def get_conversation(self, uuid_: str, limit: int = 20) -> list[dict[str, Any]]:
        msg = self.get_message(uuid_)
        if not msg:
            return []
        return self.messages.find_conversation(
            message_id=msg.get("message_id", ""),
            references=msg.get("references", ""),
            in_reply_to=msg.get("in_reply_to", ""),
            limit=limit,
        )

    def process_sync_backlog(self) -> int:
        """Process pending IMAP flag syncs."""
        return self.msg_ops.process_sync_backlog()

    # ── Message operations ───────────────────────────────────────────────

    def mark_read(self, msg_uuid: str, is_read: bool = True):
        self.msg_ops.mark_read(msg_uuid, is_read)

    def trash_message(self, msg_uuid: str):
        self.msg_ops.trash_message(msg_uuid)

    def move_message(self, msg_uuid: str, destination_folder_name: str):
        self.msg_ops.move_message(msg_uuid, destination_folder_name)

    def send_email(self, account_email: str, to: list[str], subject: str,
                   body: str = "", cc: list[str] | None = None,
                   bcc: list[str] | None = None, priority: int = 3,
                   body_format: str = "markdown",
                   attachments: list[str] | None = None,
                   signature: str | None = None,
                   in_reply_to: str | None = None) -> dict:
        return self.msg_ops.send_email(account_email, to, subject, body, cc=cc,
                                       bcc=bcc, priority=priority,
                                       body_format=body_format,
                                       attachments=attachments,
                                       signature=signature,
                                       in_reply_to=in_reply_to)

    def process_send_queue(self, limit: int = 50) -> dict:
        """Process pending send-queue entries with exponential backoff.

        Args:
            limit: Maximum number of queue entries to process.

        Returns:
            Dict with ``sent``, ``retrying``, ``failed`` counts.
        """
        return self.msg_ops.process_send_queue(limit=limit)

    # ── MessageStore protocol (used by IMAP sync) ────────────────────────

    # ── Spam block management ──────────────────────────────────────────

    @property
    def spam(self):
        """Get a SpamManager instance for the email DB."""
        from lighterbird.email.filters.spam import SpamManager

        return SpamManager(self._db)

    @property
    def db(self):
        return self._db

    # NOTE: no db setter — changing _db after construction would orphan
    # the sub-service instances (self.accounts, self.messages, etc.)
