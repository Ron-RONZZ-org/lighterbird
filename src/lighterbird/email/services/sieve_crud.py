"""Sieve script CRUD and activation management for SieveService.

Provides the ``SieveCrudMixin`` with methods for creating, reading, updating,
and deleting Sieve scripts, as well as managing per-account activations.

Methods defined here expect to be mixed into a class that sets::

    self.db   # database connection
"""

from __future__ import annotations

from typing import Any

from lighterbird.email.filters.sieve import validate_sieve


class SieveCrudMixin:
    """Mixin for Sieve script CRUD and activation management.

    Expects the host class to set ``self.db`` (database connection).
    Methods ``_now()``, ``_validate_name()``, ``_row_with_activation()``,
    ``_spam_blocks_virtual()``, ``_combine_and_sync()``, and
    ``_delete_from_remote()`` are expected via MRO from the host class.
    """

    # ── Script CRUD (global) ─────────────────────────────────────────────

    def create_script(
        self,
        name: str,
        content: str = "",
    ) -> dict[str, Any]:
        """Create a new global Sieve script.

        Args:
            name: Script name (unique, becomes the PK).
            content: Sieve script source.

        Returns:
            The new script record dict.
        """
        self._validate_name(name)
        is_valid, err = validate_sieve(content)
        if not is_valid and err:
            raise ValueError(f"Sieve syntax error: {err}")

        now = self._now()
        try:
            self.db.execute(
                "INSERT INTO sieve_scripts (name, content, system, created_at, updated_at) "
                "VALUES (?, ?, 0, ?, ?)",
                (name, content, now, now),
            )
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError(f"A script named '{name}' already exists.")
            raise
        return self.get_script(name)

    def list_scripts(self, account_email: str | None = None) -> list[dict[str, Any]]:
        """List all global scripts. If ``account_email`` is given, include
        per-account activation info as ``aktivado`` dict on each script.
        Also appends a virtual ``_spam_blocks`` entry if relevant.
        """
        if account_email:
            rows = list(
                self.db.execute(
                    "SELECT s.name, s.content, s.system, "
                    "s.created_at, s.updated_at, "
                    "a.active as akt_active, "
                    "a.priority as akt_priority, a.man_sync as akt_man_sync, "
                    "a.created_at as akt_created_at, a.updated_at as akt_updated_at "
                    "FROM sieve_scripts s "
                    "LEFT JOIN sieve_activations a ON a.script_name = s.name "
                    "AND a.account_email = ? "
                    "ORDER BY s.system DESC, s.name ASC",
                    (account_email,),
                )
            )
        else:
            rows = list(
                self.db.execute(
                    "SELECT s.name, s.content, s.system, "
                    "s.created_at, s.updated_at, "
                    "NULL as akt_active, "
                    "NULL as akt_priority, NULL as akt_man_sync, "
                    "NULL as akt_created_at, NULL as akt_updated_at "
                    "FROM sieve_scripts s ORDER BY s.system DESC, s.name ASC"
                )
            )

        scripts = [self._row_with_activation(row) for row in rows]

        # Append virtual _spam_blocks if account context given
        if account_email:
            virtual = self._spam_blocks_virtual(account_email)
            if virtual:
                scripts.append(virtual)

        return scripts

    def get_script(self, name: str) -> dict[str, Any] | None:
        """Get a global script by name, returned in response format."""
        if name == "_spam_blocks":
            return None  # virtual — use get_script_with_activation instead
        row = self.db.execute_one(
            "SELECT name, content, system, created_at, updated_at "
            "FROM sieve_scripts WHERE name = ?",
            (name,),
        )
        if not row:
            return None
        return {
            "name": row["name"],
            "content": row.get("content", ""),
            "system": bool(row.get("system", 0)),
            "created_at": row.get("created_at", ""),
            "modified_at": row.get("updated_at", ""),
            "aktivado": None,
        }

    def get_script_with_activation(
        self, name: str, account_email: str
    ) -> dict[str, Any] | None:
        """Get a script with per-account activation info."""
        if name == "_spam_blocks":
            return self._spam_blocks_virtual(account_email)

        row = self.db.execute_one(
            "SELECT s.name, s.content, s.system, "
            "s.created_at, s.updated_at, "
            "a.active as akt_active, "
            "a.priority as akt_priority, a.man_sync as akt_man_sync, "
            "a.created_at as akt_created_at, a.updated_at as akt_updated_at "
            "FROM sieve_scripts s "
            "LEFT JOIN sieve_activations a ON a.script_name = s.name "
            "AND a.account_email = ? "
            "WHERE s.name = ?",
            (account_email, name),
        )
        if not row:
            return None
        return self._row_with_activation(row)

    def update_script(
        self,
        name: str,
        new_name: str | None = None,
        content: str | None = None,
    ) -> dict[str, Any] | None:
        """Update a global script (rename and/or change content).

        Args:
            name: Current script name.
            new_name: New name (rename).
            content: New content.

        Returns:
            Updated script dict, or None if not found.
        """
        script = self.get_script(name)
        if not script:
            return None
        if script.get("system"):
            raise ValueError(f"System script '{name}' is read-only.")

        now = self._now()
        updates: dict[str, Any] = {}

        if new_name is not None:
            self._validate_name(new_name)
            updates["name"] = new_name
        if content is not None:
            is_valid, err = validate_sieve(content)
            if not is_valid and err:
                raise ValueError(f"Sieve syntax error: {err}")
            updates["content"] = content

        if not updates:
            return script

        # Rename requires PRAGMA foreign_keys=OFF to cascade to
        # sieve_activations.script_name
        if new_name is not None and new_name != name:
            self.db.execute("PRAGMA foreign_keys=OFF")
            try:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                values = [*list(updates.values()), now, name]
                self.db.execute(
                    f"UPDATE sieve_scripts SET {set_clause}, updated_at = ? "
                    "WHERE name = ?",
                    values,
                )
            finally:
                self.db.execute("PRAGMA foreign_keys=ON")
        else:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = [*list(updates.values()), now, name]
            self.db.execute(
                f"UPDATE sieve_scripts SET {set_clause}, updated_at = ? "
                "WHERE name = ?",
                values,
            )

        final_name = new_name if new_name else name
        return self.get_script(final_name)

    def delete_script(self, name: str) -> bool:
        """Delete a global script (cascades to all activations)."""
        script = self.get_script(name)
        if not script:
            return False
        if script.get("system"):
            raise ValueError(f"System script '{name}' is read-only.")

        # Collect activations for remote cleanup before cascade delete
        activations = list(
            self.db.execute(
                "SELECT a.account_email FROM sieve_activations a "
                "JOIN sieve_scripts s ON s.name = a.script_name "
                "WHERE s.name = ? AND a.man_sync = 1",
                (name,),
            )
        )
        self.db.execute("DELETE FROM sieve_scripts WHERE name = ?", (name,))
        for act in activations:
            self._delete_from_remote(act["account_email"], name)
        return True

    # ── Activation management ─────────────────────────────────────────────

    def activate_script(
        self,
        name: str,
        account_email: str,
        man_sync: bool = True,
        priority: int = 0,
    ) -> dict[str, Any] | None:
        """Activate a script for a specific account.

        Args:
            name: Script name.
            account_email: Account email.
            man_sync: Whether to include in combined remote sync.
            priority: Execution priority (lower = evaluated first).

        Returns:
            Script dict with activation info, or None if script not found.
        """
        script = self.get_script(name)
        if not script:
            return None

        now = self._now()

        # Upsert activation
        existing = self.db.execute_one(
            "SELECT 1 FROM sieve_activations "
            "WHERE script_name = ? AND account_email = ?",
            (name, account_email),
        )
        if existing:
            self.db.execute(
                "UPDATE sieve_activations SET active = 1, priority = ?, "
                "man_sync = ?, updated_at = ? "
                "WHERE script_name = ? AND account_email = ?",
                (priority, 1 if man_sync else 0, now, name, account_email),
            )
        else:
            self.db.execute(
                "INSERT INTO sieve_activations "
                "(script_name, account_email, active, priority, man_sync, "
                "created_at, updated_at) "
                "VALUES (?, ?, 1, ?, ?, ?, ?)",
                (name, account_email, priority, 1 if man_sync else 0, now, now),
            )

        # Sync combined scripts to remote
        if man_sync:
            self._combine_and_sync(account_email)

        return self.get_script_with_activation(name, account_email)

    def deactivate_script(self, name: str, account_email: str) -> dict[str, Any] | None:
        """Deactivate a script for a specific account.

        Args:
            name: Script name.
            account_email: Account email.

        Returns:
            Script dict (without activation), or None if script not found.
        """
        script = self.get_script(name)
        if not script:
            return None

        had_sync = False
        activation = self.db.execute_one(
            "SELECT man_sync FROM sieve_activations "
            "WHERE script_name = ? AND account_email = ?",
            (name, account_email),
        )
        if activation:
            had_sync = activation.get("man_sync", False)
            self.db.execute(
                "DELETE FROM sieve_activations "
                "WHERE script_name = ? AND account_email = ?",
                (name, account_email),
            )

        # Re-sync combined if there are other active scripts
        if had_sync:
            self._combine_and_sync(account_email)

        script["aktivado"] = None
        return script

    def set_priority(
        self,
        name: str,
        account_email: str,
        priority: int,
    ) -> dict[str, Any] | None:
        """Set execution priority for a script on an account."""
        now = self._now()
        self.db.execute(
            "UPDATE sieve_activations SET priority = ?, updated_at = ? "
            "WHERE script_name = ? AND account_email = ?",
            (priority, now, name, account_email),
        )
        return self.get_script_with_activation(name, account_email)

    def activate_all(self, name: str) -> dict[str, list[str]]:
        """Activate a script on all accounts that have ManageSieve configured."""
        accounts = list(
            self.db.execute(
                "SELECT email FROM accounts WHERE managesieve_host != ''"
            )
        )
        succeeded = []
        failed = []
        for acct in accounts:
            try:
                self.activate_script(name, account_email=acct["email"])
                succeeded.append(acct["email"])
            except Exception:
                failed.append(acct["email"])
        return {"succeeded": succeeded, "failed": failed}

    def deactivate_all(self, name: str) -> dict[str, list[str]]:
        """Deactivate a script on all accounts where it is active."""
        activations = list(
            self.db.execute(
                "SELECT a.account_email FROM sieve_activations a "
                "JOIN sieve_scripts s ON s.name = a.script_name "
                "WHERE s.name = ? AND a.active = 1",
                (name,),
            )
        )
        succeeded = []
        failed = []
        for act in activations:
            try:
                self.deactivate_script(name, account_email=act["account_email"])
                succeeded.append(act["account_email"])
            except Exception:
                failed.append(act["account_email"])
        return {"succeeded": succeeded, "failed": failed}

    def list_activations(self, account_email: str) -> list[dict[str, Any]]:
        """List all activations for an account, ordered by priority."""
        return list(
            self.db.execute(
                "SELECT a.*, s.content as script_content, "
                "s.system as script_system "
                "FROM sieve_activations a "
                "JOIN sieve_scripts s ON s.name = a.script_name "
                "WHERE a.account_email = ? "
                "ORDER BY a.priority ASC, s.name ASC",
                (account_email,),
            )
        )


__all__ = ["SieveCrudMixin"]
