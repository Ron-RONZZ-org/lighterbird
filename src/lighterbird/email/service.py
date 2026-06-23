"""EmailService — unified facade for email operations.

Composes AccountService, MessageService, and MessageOpsService.
"""

from __future__ import annotations

from lighterbird.email.services import AccountService, MessageService, MessageOpsService
from lighterbird.email.db import get_db


class EmailService:
    """Unified email operations facade."""

    def __init__(self, db=None):
        self.db = db or get_db()
        self.accounts = AccountService(self.db)
        self.messages = MessageService(self.db)
        self.msg_ops = MessageOpsService(self.db, self.accounts)

    # ── Account operations ───────────────────────────────────────────────

    def create_account(self, data: dict, password: str) -> dict:
        return self.accounts.create_account(data, password)

    def list_accounts(self):
        return self.accounts.list_accounts()

    def delete_account(self, uuid_: str):
        self.accounts.delete_password(uuid_)
        return self.accounts.delete(uuid_)

    def get_account(self, uuid_: str):
        return self.accounts.get_account_with_password(uuid_)

    def resolve_account(self, identifier: str):
        return self.accounts.resolve_account(identifier)

    # ── Sync ─────────────────────────────────────────────────────────────

    def sync_account(self, uuid_: str, force: bool = False):
        """Sync messages for a single account.

        Always returns a SyncResult (never raises). Errors such as
        missing account, missing password, or IMAP connection failure
        are captured in the result's ``errors`` list.
        """
        from lighterbird.email.imap import sync_account as _sync
        from lighterbird.email.imap.sync import SyncResult

        acct = self.accounts.get_account_with_password(uuid_)
        if not acct:
            result = SyncResult()
            result.errors.append(f"Account not found: {uuid_[:8]}")
            return result
        if not acct.get("password"):
            result = SyncResult()
            result.errors.append(
                f"No password configured for account {uuid_[:8]}. "
                f"Set it with: !email account modify {uuid_[:8]} --password <pw>"
            )
            return result
        try:
            result = _sync(
                host=acct.get("imap_servilo", ""),
                port=acct.get("imap_haveno", 993),
                use_ssl=acct.get("imap_ssl", 1) == 1,
                username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
                password=acct["password"],
                konto_id=uuid_,
                db_store=self,
                force=force,
            )
        except ConnectionError as e:
            result = SyncResult()
            result.errors.append(str(e))
        return result

    def sync_all(self, force: bool = False) -> dict[str, dict]:
        """Sync messages for all accounts.

        Delegates to :meth:`sync_account` per account — errors (missing
        password, IMAP failure, etc.) are captured in each result's
        ``errors`` list.
        """
        results = {}
        for acct in self.accounts.list_accounts():
            uuid_ = acct["uuid"]
            try:
                sr = self.sync_account(uuid_, force=force)
                results[uuid_] = sr.to_dict()
            except Exception as e:
                results[uuid_] = {"total": 0, "new": 0, "errors": [str(e)]}
        return results

    # ── Message queries ──────────────────────────────────────────────────

    def get_message(self, uuid_: str):
        return self.messages.get_message(uuid_)

    def list_messages(self, konto_id=None, folder=None, limit=50, offset=0):
        return self.messages.list_messages(
            konto_id=konto_id, folder=folder, limit=limit, offset=offset
        )

    def search_messages(self, filters: dict, limit=50):
        return self.messages.search_messages(filters, limit=limit)

    # ── Message operations ───────────────────────────────────────────────

    def mark_read(self, msg_uuid: str, legita: bool = True):
        self.msg_ops.mark_read(msg_uuid, legita)

    def trash_message(self, msg_uuid: str):
        self.msg_ops.trash_message(msg_uuid)

    def send_email(self, account_uuid: str, to: list[str], subject: str,
                   body: str = "", cc: list[str] | None = None):
        self.msg_ops.send_email(account_uuid, to, subject, body, cc=cc)

    # ── MessageStore protocol (used by IMAP sync) ────────────────────────

    @property
    def db(self):
        return self._db

    @db.setter
    def db(self, value):
        self._db = value
