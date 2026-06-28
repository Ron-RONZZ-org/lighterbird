"""SieveService — global Sieve script management + per-account activation.

Design:
  - Sieve scripts are **global** (stored once, not per-account).
  - Per-account activation is tracked in ``sieve_aktivadoj``.
  - This allows a script to be activated on multiple accounts.
  - Scripts are stored locally in SQLite and backed up like other data.
  - Optional ManageSieve (RFC 5804) remote sync per activation.
  - ``_spam_blocks`` is a virtual system script generated on-the-fly
    from ``SpamManager.to_sieve()`` — it is NOT stored in the DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lighterbird.email.filters.sieve import SieveManager, validate_sieve


class SieveService:
    """Manage global Sieve scripts with per-account activation."""

    SYSTEM_PREFIX = "_"

    def __init__(self, db) -> None:
        self.db = db

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _validate_name(self, nomo: str) -> None:
        """Reject names reserved for system scripts."""
        if nomo.startswith(self.SYSTEM_PREFIX):
            raise ValueError(
                f"Script name '{nomo}' starts with '{self.SYSTEM_PREFIX}' "
                f"which is reserved for system scripts."
            )

    def _resolve_account(self, identifier: str) -> dict[str, Any] | None:
        """Resolve an account by email or UUID prefix."""
        if not identifier:
            return None
        # Try exact email match first (kontoj PK is now retposto)
        row = self.db.execute_one(
            "SELECT retposto, managesieve_host, managesieve_port, "
            "managesieve_use_tls FROM kontoj WHERE retposto = ?",
            (identifier.lower().strip(),),
        )
        if row:
            return row
        # Try email match
        row = self.db.execute_one(
            "SELECT retposto, managesieve_host, managesieve_port, "
            "managesieve_use_tls FROM kontoj WHERE retposto LIKE ? || '%'",
            (identifier,),
        )
        return row

    def _get_managesieve_config(self, konto_id: str) -> dict[str, Any] | None:
        row = self.db.execute_one(
            "SELECT managesieve_host, managesieve_port, managesieve_use_tls "
            "FROM kontoj WHERE retposto = ?",
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
        from lighterbird.email.keyring import get_password

        try:
            return get_password(konto_id)
        except Exception:
            return None

    def _sync_to_remote(self, konto_id: str, nomo: str, content: str) -> None:
        """Sync a script to the remote ManageSieve server for one account."""
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
                mgr.put_script(nomo, content)
            finally:
                mgr.disconnect()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "ManageSieve sync failed for %s@%s script %s",
                konto_id,
                nomo,
            )

    def _delete_from_remote(self, konto_id: str, nomo: str) -> None:
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
                "ManageSieve delete failed for %s@%s", konto_id, nomo,
            )

    def _activate_on_remote(self, konto_id: str, nomo: str) -> None:
        """Activate a script on the remote ManageSieve server."""
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
                mgr.activate_script(nomo)
            finally:
                mgr.disconnect()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "ManageSieve activate failed for %s@%s", konto_id, nomo,
            )

    # ── Spam blocks (virtual script) ─────────────────────────────────────

    def _spam_blocks_virtual(self, konto_id: str) -> dict[str, Any] | None:
        """Return the virtual ``_spam_blocks`` script for an account, or None."""
        try:
            from lighterbird.email.filters.spam import SpamManager

            mgr = SpamManager(self.db)
            blocks = list(mgr.list_blocks())
            if not blocks:
                return None
            content = mgr.to_sieve()
            if not content:
                return None
        except Exception:
            return None

        return {
            "name": "_spam_blocks",
            "content": content,
            "system": 1,
            "created_at": "",
            "modified_at": "",
            "aktivado": None,
        }

    # ── Script CRUD (global) ─────────────────────────────────────────────

    def create_script(
        self,
        nomo: str,
        content: str = "",
    ) -> dict[str, Any]:
        """Create a new global Sieve script.

        Args:
            nomo: Script name (unique, becomes the PK).
            content: Sieve script source.

        Returns:
            The new script record dict.
        """
        self._validate_name(nomo)
        is_valid, err = validate_sieve(content)
        if not is_valid and err:
            raise ValueError(f"Sieve syntax error: {err}")

        now = self._now()
        try:
            self.db.execute(
                "INSERT INTO sieve_skriptoj (nomo, content, system, kreita_je, modifita_je) "
                "VALUES (?, ?, 0, ?, ?)",
                (nomo, content, now, now),
            )
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError(f"A script named '{nomo}' already exists.")
            raise
        return self.get_script(nomo)

    def list_scripts(self, konto_id: str | None = None) -> list[dict[str, Any]]:
        """List all global scripts. If ``konto_id`` is given, include
        per-account activation info as ``aktivado`` dict on each script.
        Also appends a virtual ``_spam_blocks`` entry if relevant.
        """
        if konto_id:
            rows = list(
                self.db.execute(
                    "SELECT s.nomo, s.content, s.system, "
                    "s.kreita_je, s.modifita_je, "
                    "a.active as akt_active, "
                    "a.priority as akt_priority, a.man_sync as akt_man_sync, "
                    "a.kreita_je as akt_kreita_je, a.modifita_je as akt_modifita_je "
                    "FROM sieve_skriptoj s "
                    "LEFT JOIN sieve_aktivadoj a ON a.skripto_nomo = s.nomo "
                    "AND a.konto_id = ? "
                    "ORDER BY s.system DESC, s.nomo ASC",
                    (konto_id,),
                )
            )
        else:
            rows = list(
                self.db.execute(
                    "SELECT s.nomo, s.content, s.system, "
                    "s.kreita_je, s.modifita_je, "
                    "NULL as akt_active, "
                    "NULL as akt_priority, NULL as akt_man_sync, "
                    "NULL as akt_kreita_je, NULL as akt_modifita_je "
                    "FROM sieve_skriptoj s ORDER BY s.system DESC, s.nomo ASC"
                )
            )

        scripts = [self._row_with_activation(row) for row in rows]

        # Append virtual _spam_blocks if account context given
        if konto_id:
            virtual = self._spam_blocks_virtual(konto_id)
            if virtual:
                scripts.append(virtual)

        return scripts

    def get_script(self, nomo: str) -> dict[str, Any] | None:
        """Get a global script by name, returned in response format."""
        if nomo == "_spam_blocks":
            return None  # virtual — use get_script_with_activation instead
        row = self.db.execute_one(
            "SELECT nomo, content, system, kreita_je, modifita_je "
            "FROM sieve_skriptoj WHERE nomo = ?",
            (nomo,),
        )
        if not row:
            return None
        return {
            "name": row["nomo"],
            "content": row.get("content", ""),
            "system": bool(row.get("system", 0)),
            "created_at": row.get("kreita_je", ""),
            "modified_at": row.get("modifita_je", ""),
            "aktivado": None,
        }

    def get_script_with_activation(
        self, nomo: str, konto_id: str
    ) -> dict[str, Any] | None:
        """Get a script with per-account activation info."""
        if nomo == "_spam_blocks":
            return self._spam_blocks_virtual(konto_id)

        row = self.db.execute_one(
            "SELECT s.nomo, s.content, s.system, "
            "s.kreita_je, s.modifita_je, "
            "a.active as akt_active, "
            "a.priority as akt_priority, a.man_sync as akt_man_sync, "
            "a.kreita_je as akt_kreita_je, a.modifita_je as akt_modifita_je "
            "FROM sieve_skriptoj s "
            "LEFT JOIN sieve_aktivadoj a ON a.skripto_nomo = s.nomo "
            "AND a.konto_id = ? "
            "WHERE s.nomo = ?",
            (konto_id, nomo),
        )
        if not row:
            return None
        return self._row_with_activation(row)

    def update_script(
        self,
        nomo: str,
        new_name: str | None = None,
        content: str | None = None,
    ) -> dict[str, Any] | None:
        """Update a global script (rename and/or change content).

        Args:
            nomo: Current script name.
            new_name: New name (rename).
            content: New content.

        Returns:
            Updated script dict, or None if not found.
        """
        script = self.get_script(nomo)
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

        if not updates:
            return script

        # Rename requires PRAGMA foreign_keys=OFF to cascade to
        # sieve_aktivadoj.skripto_nomo
        if new_name is not None and new_name != nomo:
            self.db.execute("PRAGMA foreign_keys=OFF")
            try:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                values = list(updates.values()) + [now, nomo]
                self.db.execute(
                    f"UPDATE sieve_skriptoj SET {set_clause}, modifita_je = ? "
                    "WHERE nomo = ?",
                    values,
                )
            finally:
                self.db.execute("PRAGMA foreign_keys=ON")
        else:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [now, nomo]
            self.db.execute(
                f"UPDATE sieve_skriptoj SET {set_clause}, modifita_je = ? "
                "WHERE nomo = ?",
                values,
            )

        final_name = new_name if new_name else nomo
        return self.get_script(final_name)

    def delete_script(self, nomo: str) -> bool:
        """Delete a global script (cascades to all activations)."""
        script = self.get_script(nomo)
        if not script:
            return False
        if script.get("system"):
            raise ValueError(f"System script '{nomo}' is read-only.")

        # Collect activations for remote cleanup before cascade delete
        activations = list(
            self.db.execute(
                "SELECT a.konto_id FROM sieve_aktivadoj a "
                "JOIN sieve_skriptoj s ON s.nomo = a.skripto_nomo "
                "WHERE s.nomo = ? AND a.man_sync = 1",
                (nomo,),
            )
        )
        self.db.execute("DELETE FROM sieve_skriptoj WHERE nomo = ?", (nomo,))
        for act in activations:
            self._delete_from_remote(act["konto_id"], nomo)
        return True

    # ── Activation management ─────────────────────────────────────────────

    def _combine_and_sync(self, konto_id: str) -> None:
        """Combine all active scripts for an account and sync to ManageSieve."""
        from lighterbird.email.filters.combiner import combine_scripts
        from lighterbird.email.filters.sieve import validate_sieve

        rows = list(
            self.db.execute(
                "SELECT s.nomo, s.content FROM sieve_aktivadoj a "
                "JOIN sieve_skriptoj s ON s.nomo = a.skripto_nomo "
                "WHERE a.konto_id = ? AND a.active = 1 AND a.man_sync = 1 "
                "ORDER BY a.priority ASC, s.nomo ASC",
                (konto_id,),
            )
        )
        if not rows:
            return

        scripts = [{"name": r["nomo"], "content": r["content"]} for r in rows]
        combined, _warnings = combine_scripts(scripts)

        is_valid, err = validate_sieve(combined)
        if not is_valid and err:
            import logging

            logging.getLogger(__name__).warning(
                "Combined sieve script validation failed for %s: %s",
                konto_id,
                err,
            )
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
                mgr.put_script("_combined", combined)
                mgr.activate_script("_combined")
            finally:
                mgr.disconnect()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "ManageSieve combine-sync failed for %s", konto_id,
            )

    def activate_script(
        self,
        nomo: str,
        konto_id: str,
        man_sync: bool = True,
        priority: int = 0,
    ) -> dict[str, Any] | None:
        """Activate a script for a specific account.

        Args:
            nomo: Script name.
            konto_id: Account email.
            man_sync: Whether to include in combined remote sync.
            priority: Execution priority (lower = evaluated first).

        Returns:
            Script dict with activation info, or None if script not found.
        """
        script = self.get_script(nomo)
        if not script:
            return None

        now = self._now()

        # Upsert activation
        existing = self.db.execute_one(
            "SELECT 1 FROM sieve_aktivadoj "
            "WHERE skripto_nomo = ? AND konto_id = ?",
            (nomo, konto_id),
        )
        if existing:
            self.db.execute(
                "UPDATE sieve_aktivadoj SET active = 1, priority = ?, "
                "man_sync = ?, modifita_je = ? "
                "WHERE skripto_nomo = ? AND konto_id = ?",
                (priority, 1 if man_sync else 0, now, nomo, konto_id),
            )
        else:
            self.db.execute(
                "INSERT INTO sieve_aktivadoj "
                "(skripto_nomo, konto_id, active, priority, man_sync, "
                "kreita_je, modifita_je) "
                "VALUES (?, ?, 1, ?, ?, ?, ?)",
                (nomo, konto_id, priority, 1 if man_sync else 0, now, now),
            )

        # Sync combined scripts to remote
        if man_sync:
            self._combine_and_sync(konto_id)

        return self.get_script_with_activation(nomo, konto_id)

    def deactivate_script(self, nomo: str, konto_id: str) -> dict[str, Any] | None:
        """Deactivate a script for a specific account.

        Args:
            nomo: Script name.
            konto_id: Account email.

        Returns:
            Script dict (without activation), or None if script not found.
        """
        script = self.get_script(nomo)
        if not script:
            return None

        had_sync = False
        activation = self.db.execute_one(
            "SELECT man_sync FROM sieve_aktivadoj "
            "WHERE skripto_nomo = ? AND konto_id = ?",
            (nomo, konto_id),
        )
        if activation:
            had_sync = activation.get("man_sync", False)
            self.db.execute(
                "DELETE FROM sieve_aktivadoj "
                "WHERE skripto_nomo = ? AND konto_id = ?",
                (nomo, konto_id),
            )

        # Re-sync combined if there are other active scripts
        if had_sync:
            self._combine_and_sync(konto_id)

        script["aktivado"] = None
        return script

    def set_priority(
        self,
        nomo: str,
        konto_id: str,
        priority: int,
    ) -> dict[str, Any] | None:
        """Set execution priority for a script on an account."""
        now = self._now()
        self.db.execute(
            "UPDATE sieve_aktivadoj SET priority = ?, modifita_je = ? "
            "WHERE skripto_nomo = ? AND konto_id = ?",
            (priority, now, nomo, konto_id),
        )
        return self.get_script_with_activation(nomo, konto_id)

    def activate_all(self, nomo: str) -> dict[str, list[str]]:
        """Activate a script on all accounts that have ManageSieve configured."""
        accounts = list(
            self.db.execute(
                "SELECT retposto FROM kontoj WHERE managesieve_host != ''"
            )
        )
        succeeded = []
        failed = []
        for acct in accounts:
            try:
                self.activate_script(nomo, konto_id=acct["retposto"])
                succeeded.append(acct["retposto"])
            except Exception:
                failed.append(acct["retposto"])
        return {"succeeded": succeeded, "failed": failed}

    def deactivate_all(self, nomo: str) -> dict[str, list[str]]:
        """Deactivate a script on all accounts where it is active."""
        activations = list(
            self.db.execute(
                "SELECT a.konto_id FROM sieve_aktivadoj a "
                "JOIN sieve_skriptoj s ON s.nomo = a.skripto_nomo "
                "WHERE s.nomo = ? AND a.active = 1",
                (nomo,),
            )
        )
        succeeded = []
        failed = []
        for act in activations:
            try:
                self.deactivate_script(nomo, konto_id=act["konto_id"])
                succeeded.append(act["konto_id"])
            except Exception:
                failed.append(act["konto_id"])
        return {"succeeded": succeeded, "failed": failed}

    def list_activations(self, konto_id: str) -> list[dict[str, Any]]:
        """List all activations for an account, ordered by priority."""
        return list(
            self.db.execute(
                "SELECT a.*, s.content as script_content, "
                "s.system as script_system "
                "FROM sieve_aktivadoj a "
                "JOIN sieve_skriptoj s ON s.nomo = a.skripto_nomo "
                "WHERE a.konto_id = ? "
                "ORDER BY a.priority ASC, s.nomo ASC",
                (konto_id,),
            )
        )

    # ── Spam block integration ───────────────────────────────────────────

    def upsert_spam_blocks(self, konto_id: str, content: str) -> dict[str, Any]:
        """No-op: ``_spam_blocks`` is now virtual."""
        return {"name": "_spam_blocks", "content": content, "system": 1}

    # ── Row helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _row_with_activation(row: dict) -> dict[str, Any]:
        """Convert a joined DB row to a response dict with nested aktivado."""
        akt = None
        if row.get("akt_active") is not None:
            akt = {
                "active": bool(row["akt_active"]),
                "priority": row.get("akt_priority", 0),
                "man_sync": bool(row.get("akt_man_sync", 1)),
                "created_at": row.get("akt_kreita_je", ""),
                "modified_at": row.get("akt_modifita_je", ""),
            }
        return {
            "name": row["nomo"],
            "content": row.get("content", ""),
            "system": bool(row.get("system", 0)),
            "created_at": row.get("kreita_je", ""),
            "modified_at": row.get("modifita_je", ""),
            "aktivado": akt,
        }


__all__ = ["SieveService"]
