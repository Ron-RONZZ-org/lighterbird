"""Account management service.

Flat service class (not mixin), forked from A-lien's RetpostoAccountsMixin.
"""

from __future__ import annotations

from typing import Any

from lighterbird.core.crud import CRUDService
from lighterbird.email.keyring import (
    get_password as _get_keyring_pw,
    set_password as _set_keyring_pw,
    delete_password as _del_keyring_pw,
)


class AccountService(CRUDService):
    """Email account CRUD with keyring password storage."""

    def __init__(self, db):
        super().__init__(db, "kontoj")

    def get_password(self, account_uuid: str) -> str | None:
        """Retrieve account password from system keyring."""
        return _get_keyring_pw(account_uuid)

    def set_password(self, account_uuid: str, password: str) -> bool:
        """Store account password in system keyring."""
        return _set_keyring_pw(account_uuid, password)

    def delete_password(self, account_uuid: str) -> bool:
        """Remove account password from system keyring."""
        return _del_keyring_pw(account_uuid)

    def create_account(self, data: dict[str, Any], password: str) -> dict[str, Any]:
        """Create a new email account with password in keyring."""
        data.pop("pasvorto", None)
        account = self.create(data)
        self.set_password(account["uuid"], password)
        return account

    def list_accounts(self) -> list[dict[str, Any]]:
        """List all accounts (password never included)."""
        return self.list(order_by="ordo", desc=False)

    def get_account_with_password(self, uuid_: str) -> dict[str, Any] | None:
        """Get account config with password from keyring.

        Returns the account dict with ``"password"`` key (or ``""`` if
        no password is stored), or None if the account does not exist.
        """
        acct = self.get(uuid_)
        if acct is None:
            return None
        pw = self.get_password(uuid_)
        acct["password"] = pw or ""
        return acct

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        """Find an account by its email address."""
        return self.db.execute_one(
            "SELECT * FROM kontoj WHERE retposto = ?", (email,)
        )

    def resolve_account(self, identifier: str) -> dict[str, Any] | None:
        """Resolve an account identifier to an account dict.

        Tries: exact UUID, UUID prefix, email match.
        """
        acct = self.get(identifier)
        if acct:
            return acct
        matches = self.find_by_uuid_prefix(identifier)
        if len(matches) == 1:
            return matches[0]
        if "@" in identifier:
            return self.find_by_email(identifier)
        return None
