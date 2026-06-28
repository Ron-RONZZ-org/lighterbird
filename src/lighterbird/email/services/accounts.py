"""Account management service.

Flat service class (not mixin), forked from A-lien's RetpostoAccountsMixin.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lighterbird.core.crud import CRUDService
from lighterbird.email.keyring import (
    get_password as _get_keyring_pw,
    set_password as _set_keyring_pw,
    delete_password as _del_keyring_pw,
)


class AccountService(CRUDService):
    """Email account CRUD with keyring password storage.

    Uses ``retposto`` (email) as primary key instead of UUID.
    """

    def __init__(self, db):
        super().__init__(db, "kontoj")

    # ── PK overrides (kontoj uses retposto, not uuid) ────────────────────

    def get(self, email: str) -> dict[str, Any] | None:
        """Get an account by email (lowercased)."""
        return self.db.execute_one(
            "SELECT * FROM kontoj WHERE retposto = ?", (email.lower().strip(),)
        )

    def update(self, email: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an account by email, preserving creation timestamp."""
        old_data = self.get(email)
        data["modifita_je"] = datetime.now(timezone.utc).isoformat()

        set_clauses = [f"{k} = ?" for k in data]
        values = list(data.values()) + [email.lower().strip()]
        self.db.execute(
            f"UPDATE {self.table} SET {', '.join(set_clauses)} WHERE retposto = ?",
            values,
        )
        self._post_update(email, old_data, data)
        return {**(old_data or {}), **data}

    def delete(self, email: str) -> bool:
        """Delete an account by email. CASCADE handles children."""
        old_data = self.get(email)
        if not old_data:
            return False
        self.db.execute(
            "DELETE FROM kontoj WHERE retposto = ?", (email.lower().strip(),)
        )
        self._post_delete(email, old_data)
        return True

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new account with retposto as PK (no UUID)."""
        now = datetime.now(timezone.utc).isoformat()
        # Normalize email to lowercase
        if "retposto" in data:
            data["retposto"] = data["retposto"].lower().strip()
        data.setdefault("kreita_je", now)
        data["modifita_je"] = now

        columns = [k for k in data if k != "uuid"]
        values = [data[k] for k in columns]
        placeholders = ", ".join(["?"] * len(columns))
        sql = (
            f"INSERT INTO {self.table} ({', '.join(columns)}) "
            f"VALUES ({placeholders})"
        )

        with self.db.transaction() as conn:
            conn.execute(sql, values)

        result = {k: data[k] for k in columns}
        self._post_create(data, result)
        return result

    # ── Password management ──────────────────────────────────────────────

    def get_password(self, account_email: str) -> str | None:
        """Retrieve account password from system keyring."""
        return _get_keyring_pw(account_email)

    def set_password(self, account_email: str, password: str) -> bool:
        """Store account password in system keyring."""
        return _set_keyring_pw(account_email, password)

    def delete_password(self, account_email: str) -> bool:
        """Remove account password from system keyring."""
        return _del_keyring_pw(account_email)

    # ── Account operations ───────────────────────────────────────────────

    def create_account(self, data: dict[str, Any], password: str) -> dict[str, Any]:
        """Create a new email account with password in keyring.

        Returns:
            The created account dict.

        Raises:
            RuntimeError: If a password was provided but the system keyring
                is unavailable or fails to store it.
        """
        data.pop("pasvorto", None)
        if "uuid" in data:
            data.pop("uuid")
        account = self.create(data)
        if password:
            if not self.set_password(account["retposto"], password):
                # Roll back the created account since we can't store the password
                self.delete(account["retposto"])
                raise RuntimeError(
                    "System keyring is unavailable — cannot store account password. "
                    "Install a keyring backend (e.g. 'sudo apt install gnome-keyring' "
                    "or set up secret-service). Alternatively, re-run the add command "
                    "without a password and use '!email account modify <email> --password <pw>' "
                    "once keyring is working."
                )
        return account

    def list_accounts(self) -> list[dict[str, Any]]:
        """List all accounts (password never included)."""
        return self.list(order_by="ordo", desc=False)

    def get_account_with_password(self, email: str) -> dict[str, Any] | None:
        """Get account config with password from keyring.

        Returns the account dict with ``"password"`` key (or ``""`` if
        no password is stored), or None if the account does not exist.
        """
        acct = self.get(email)
        if acct is None:
            return None
        pw = self.get_password(email)
        acct["password"] = pw or ""
        return acct

    def resolve_account(self, identifier: str) -> dict[str, Any] | None:
        """Resolve an account identifier to an account dict.

        Tries: exact email match, prefix match.
        """
        email = identifier.lower().strip()
        acct = self.get(email)
        if acct:
            return acct
        # Prefix match for convenience
        if "@" in email:
            return None  # No prefix matching with full email
        matches = self.db.execute(
            "SELECT * FROM kontoj WHERE retposto LIKE ? ORDER BY retposto LIMIT 10",
            (f"{email}%",),
        )
        if len(matches) == 1:
            return matches[0]
        return None
