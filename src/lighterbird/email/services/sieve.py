"""SieveService — local Sieve script CRUD + ManageSieve sync.

Provides create, read, update, delete, and activate operations on Sieve
scripts stored in the local email database, with optional sync to a
remote ManageSieve (RFC 5804) server.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from lighterbird.email.filters.sieve import SieveManager, validate_sieve


class SieveService:
    """Manage Sieve scripts locally with optional ManageSieve remote sync."""

    SYSTEM_PREFIX = "_"

    def __init__(self, db) -> None:
        self.db = db

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _validate_name(self, nomo: str) -> None:
        """Reject names that are reserved for system scripts."""
        if nomo.startswith(self.SYSTEM_PREFIX):
            raise ValueError(
                f"Script name '{nomo}' starts with '{self.SYSTEM_PREFIX}' "
                f"which is reserved for system scripts."
            )

    def _get_managesieve_config(self, konto_id: str) -> dict[str, Any] | None:
        """Return ManageSieve connection details for an account, or None."""
        row = self.db.execute_one(
            "SELECT managesieve_host, managesieve_port, managesieve_use_tls "
            "FROM kontoj WHERE uuid = ?",
            (konto_id,),
        )
        if row and row.get("managesieve_host"):
            return {
                "host": row["managesieve_host"],
                "port": row.get("managesieve_port", 4190),
                "use_tls": bool(row.get("managesieve_use_tls", 1)),
            }
        return None

    def _get_account_password(self, konto_id: str) -> str | None:
        """Get the account's IMAP password (used for ManageSieve auth too)."""
        from lighterbird.email.keyring import get_password

        try:
            return get_password(konto_id)
        except Exception:
            return None

    def _sync_to_remote(self, konto_id: str, script: dict[str, Any]) -> None:
        """Sync a single script to the remote ManageSieve server.

        Failures are caught and silently logged — local state is authoritative.
        """
        if not script.get("man_sync", 1):
            return
        cfg = self._get_managesieve_config(konto_id)
        if not cfg:
            return
        password = self._get_account_password(konto_id)
        if not password:
            return

        try:
            mgr = SieveManager(cfg["host"], port=cfg["port"], use_tls=cfg["use_tls"])
            mgr.connect(konto_id, password)
            try:
                mgr.put_script(script["nomo"], script["content"])
                if script.get("active"):
                    mgr.activate_script(script["nomo"])
            finally:
                mgr.disconnect()
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "ManageSieve sync failed for account %s script %s",
                konto_id[:8], script.get("nomo", "?"),
            )

    def _delete_from_remote(self, konto_id: str, nomo: str) -> None:
        """Delete a script from the remote ManageSieve server."""
        cfg = self._get_managesieve_config(konto_id)
        if not cfg:
            return
        password = self._get_account_password(konto_id)
        if not password:
            return

        try:
            mgr = SieveManager(cfg["host"], port=cfg["port"], use_tls=cfg["use_tls"])
            mgr.connect(konto_id, password)
            try:
                mgr.delete_script(nomo)
            finally:
                mgr.disconnect()
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "ManageSieve delete failed for account %s script %s",
                konto_id[:8], nomo,
            )

    def _deactivate_remote(self, konto_id: str) -> None:
        """Deactivate the currently active script on the remote server.
        
        We do this by activating a dummy script — or we can just leave 
        the old active script in place. The recommended approach on script
        delete is to activate another script if one exists.
        """

    # ── CRUD ─────────────────────────────────────────────────────────────

    def create_script(
        self,
        konto_id: str,
        nomo: str,
        content: str = "",
        active: bool = False,
        man_sync: bool = True,
    ) -> dict[str, Any]:
        """Create a new Sieve script.

        Args:
            konto_id: Account UUID.
            nomo: Script name.
            content: Sieve script source.
            active: Whether to activate immediately.
            man_sync: Whether to sync to remote ManageSieve.

        Returns:
            The newly created script record dict.
        """
        self._validate_name(nomo)
        is_valid, err = validate_sieve(content)
        if not is_valid and err:
            raise ValueError(f"Sieve syntax error: {err}")

        now = self._now()
        script_uuid = str(uuid.uuid4())

        # Deactivate any previously active script for this account
        if active:
            self.db.execute(
                "UPDATE sieve_skriptoj SET active = 0, modifita_je = ? "
                "WHERE konto_id = ? AND active = 1",
                (now, konto_id),
            )

        self.db.execute(
            "INSERT INTO sieve_skriptoj "
            "(uuid, konto_id, nomo, content, active, man_sync, kreita_je, modifita_je) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (script_uuid, konto_id, nomo, content, 1 if active else 0,
             1 if man_sync else 0, now, now),
        )

        script = self.db.execute_one(
            "SELECT * FROM sieve_skriptoj WHERE uuid = ?", (script_uuid,)
        )
        if script and man_sync:
            self._sync_to_remote(konto_id, script)
        return script

    def list_scripts(self, konto_id: str | None = None) -> list[dict[str, Any]]:
        """List Sieve scripts, optionally filtered by account."""
        if konto_id:
            return list(self.db.execute(
                "SELECT * FROM sieve_skriptoj WHERE konto_id = ? "
                "ORDER BY system DESC, nomo ASC",
                (konto_id,),
            ))
        return list(self.db.execute(
            "SELECT * FROM sieve_skriptoj ORDER BY konto_id, system DESC, nomo ASC"
        ))

    def get_script(self, nomo: str, konto_id: str | None = None) -> dict[str, Any] | None:
        """Get a script by name, optionally scoped to an account."""
        if konto_id:
            return self.db.execute_one(
                "SELECT * FROM sieve_skriptoj WHERE nomo = ? AND konto_id = ?",
                (nomo, konto_id),
            )
        return self.db.execute_one(
            "SELECT * FROM sieve_skriptoj WHERE nomo = ?", (nomo,)
        )

    def update_script(
        self,
        nomo: str,
        konto_id: str,
        new_name: str | None = None,
        content: str | None = None,
        active: bool | None = None,
        man_sync: bool | None = None,
    ) -> dict[str, Any] | None:
        """Update a Sieve script.

        Args:
            nomo: Current script name.
            konto_id: Account UUID.
            new_name: New script name (rename).
            content: New script content.
            active: Activate/deactivate.
            man_sync: Enable/disable remote sync.

        Returns:
            Updated script record dict, or None if not found.
        """
        script = self.get_script(nomo, konto_id)
        if not script:
            return None
        if script.get("system"):
            raise ValueError(f"System script '{nomo}' is read-only.")

        now = self._now()
        updates: dict[str, Any] = {}

        if new_name is not None:
            self._validate_name(new_name)
            updates["nomo"] = new_name
        if content is not None:
            is_valid, err = validate_sieve(content)
            if not is_valid and err:
                raise ValueError(f"Sieve syntax error: {err}")
            updates["content"] = content
        if active is not None:
            # Deactivate others if activating
            if active:
                self.db.execute(
                    "UPDATE sieve_skriptoj SET active = 0, modifita_je = ? "
                    "WHERE konto_id = ? AND active = 1 AND nomo != ?",
                    (now, konto_id, nomo),
                )
            updates["active"] = 1 if active else 0
        if man_sync is not None:
            updates["man_sync"] = 1 if man_sync else 0

        if not updates:
            return script

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [now, nomo, konto_id]
        self.db.execute(
            f"UPDATE sieve_skriptoj SET {set_clause}, modifita_je = ? "
            "WHERE nomo = ? AND konto_id = ?",
            values,
        )

        updated = self.get_script(updates.get("nomo", nomo), konto_id)
        if updated and script.get("man_sync", 1):
            self._sync_to_remote(konto_id, updated)
        return updated

    def delete_script(self, nomo: str, konto_id: str) -> bool:
        """Delete a Sieve script.

        Args:
            nomo: Script name.
            konto_id: Account UUID.

        Returns:
            True if deleted, False if not found.
        """
        script = self.get_script(nomo, konto_id)
        if not script:
            return False
        if script.get("system"):
            raise ValueError(f"System script '{nomo}' is read-only.")

        self.db.execute(
            "DELETE FROM sieve_skriptoj WHERE nomo = ? AND konto_id = ?",
            (nomo, konto_id),
        )

        if script.get("man_sync", 1):
            self._delete_from_remote(konto_id, nomo)

        # If the deleted script was active, activate another one if available
        if script.get("active"):
            remaining = self.db.execute_one(
                "SELECT nomo FROM sieve_skriptoj WHERE konto_id = ? AND active = 0 "
                "ORDER BY system DESC, nomo ASC LIMIT 1",
                (konto_id,),
            )
            if remaining:
                self.activate_script(remaining["nomo"], konto_id)

        return True

    def activate_script(self, nomo: str, konto_id: str) -> dict[str, Any] | None:
        """Activate a Sieve script, deactivating any previously active one.

        Args:
            nomo: Script name to activate.
            konto_id: Account UUID.

        Returns:
            Updated script record, or None if not found.
        """
        script = self.get_script(nomo, konto_id)
        if not script:
            return None

        now = self._now()
        self.db.execute(
            "UPDATE sieve_skriptoj SET active = 0, modifita_je = ? "
            "WHERE konto_id = ? AND active = 1",
            (now, konto_id),
        )
        self.db.execute(
            "UPDATE sieve_skriptoj SET active = 1, modifita_je = ? "
            "WHERE nomo = ? AND konto_id = ?",
            (now, nomo, konto_id),
        )

        updated = self.get_script(nomo, konto_id)
        if updated and script.get("man_sync", 1):
            self._sync_to_remote(konto_id, updated)
        return updated

    # ── Spam block integration ───────────────────────────────────────────

    def upsert_spam_blocks(self, konto_id: str, content: str) -> dict[str, Any]:
        """Create or update the ``_spam_blocks`` system script.

        Called automatically by ``SpamManager`` whenever blocks change.
        """
        existing = self.db.execute_one(
            "SELECT * FROM sieve_skriptoj WHERE nomo = '_spam_blocks' AND konto_id = ?",
            (konto_id,),
        )
        now = self._now()

        if existing:
            self.db.execute(
                "UPDATE sieve_skriptoj SET content = ?, modifita_je = ? "
                "WHERE uuid = ?",
                (content, now, existing["uuid"]),
            )
            updated = self.get_script("_spam_blocks", konto_id)
            if updated and existing.get("man_sync", 1):
                self._sync_to_remote(konto_id, updated)
            return updated

        script_uuid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO sieve_skriptoj "
            "(uuid, konto_id, nomo, content, active, system, man_sync, kreita_je, modifita_je) "
            "VALUES (?, ?, '_spam_blocks', ?, 0, 1, 1, ?, ?)",
            (script_uuid, konto_id, content, now, now),
        )
        script = self.get_script("_spam_blocks", konto_id)
        if script:
            self._sync_to_remote(konto_id, script)
        return script


__all__ = ["SieveService"]
