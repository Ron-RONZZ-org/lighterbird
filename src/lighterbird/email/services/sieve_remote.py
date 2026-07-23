"""ManageSieve remote sync operations for SieveService.

Provides the ``SieveRemoteMixin`` with helpers for managing Sieve scripts
on remote ManageSieve servers (RFC 5804).

Methods defined here expect to be mixed into a class that sets::

    self.db   # database connection
"""

from __future__ import annotations

from typing import Any

from lighterbird.email.filters.sieve import SieveManager


class SieveRemoteMixin:
    """Mixin providing remote ManageSieve sync operations.

    Expects the host class to set ``self.db`` (database connection).
    """

    def _resolve_account(self, identifier: str) -> dict[str, Any] | None:
        """Resolve an account by email or UUID prefix."""
        if not identifier:
            return None
        # Try exact email match first (accounts PK is now email)
        row = self.db.execute_one(
            "SELECT email, managesieve_host, managesieve_port, "
            "managesieve_use_tls FROM accounts WHERE email = ?",
            (identifier.lower().strip(),),
        )
        if row:
            return row
        # Try email match
        row = self.db.execute_one(
            "SELECT email, managesieve_host, managesieve_port, "
            "managesieve_use_tls FROM accounts WHERE email LIKE ? || '%'",
            (identifier,),
        )
        return row

    def _get_managesieve_config(self, account_email: str) -> dict[str, Any] | None:
        row = self.db.execute_one(
            "SELECT managesieve_host, managesieve_port, managesieve_use_tls "
            "FROM accounts WHERE email = ?",
            (account_email,),
        )
        if row and row.get("managesieve_host"):
            return {
                "host": row["managesieve_host"],
                "port": row.get("managesieve_port", 4190),
                "use_tls": bool(row.get("managesieve_use_tls", 1)),
            }
        return None

    def _get_account_password(self, account_email: str) -> str | None:
        from lighterbird.email.keyring import get_password

        try:
            return get_password(account_email)
        except Exception:
            return None

    def _sync_to_remote(self, account_email: str, name: str, content: str) -> None:
        """Sync a script to the remote ManageSieve server for one account."""
        cfg = self._get_managesieve_config(account_email)
        if not cfg:
            return
        password = self._get_account_password(account_email)
        if not password:
            return
        try:
            mgr = SieveManager(cfg["host"], port=cfg["port"], use_tls=cfg["use_tls"])
            mgr.connect(account_email, password)
            try:
                mgr.put_script(name, content)
            finally:
                mgr.disconnect()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "ManageSieve sync failed for %s@%s script %s",
                account_email,
                name,
            )

    def _delete_from_remote(self, account_email: str, name: str) -> None:
        cfg = self._get_managesieve_config(account_email)
        if not cfg:
            return
        password = self._get_account_password(account_email)
        if not password:
            return
        try:
            mgr = SieveManager(cfg["host"], port=cfg["port"], use_tls=cfg["use_tls"])
            mgr.connect(account_email, password)
            try:
                mgr.delete_script(name)
            finally:
                mgr.disconnect()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "ManageSieve delete failed for %s@%s", account_email, name,
            )

    def _activate_on_remote(self, account_email: str, name: str) -> None:
        """Activate a script on the remote ManageSieve server."""
        cfg = self._get_managesieve_config(account_email)
        if not cfg:
            return
        password = self._get_account_password(account_email)
        if not password:
            return
        try:
            mgr = SieveManager(cfg["host"], port=cfg["port"], use_tls=cfg["use_tls"])
            mgr.connect(account_email, password)
            try:
                mgr.activate_script(name)
            finally:
                mgr.disconnect()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "ManageSieve activate failed for %s@%s", account_email, name,
            )

    def _combine_and_sync(self, account_email: str) -> None:
        """Combine all active scripts for an account and sync to ManageSieve.

        Automatically includes the virtual ``_spam_blocks`` script (generated
        from the blocklist) so that sender/domain blocks are enforced
        server-side.
        """
        from lighterbird.email.filters.combiner import combine_scripts
        from lighterbird.email.filters.sieve import validate_sieve

        rows = list(
            self.db.execute(
                "SELECT s.name, s.content FROM sieve_activations a "
                "JOIN sieve_scripts s ON s.name = a.script_name "
                "WHERE a.account_email = ? AND a.active = 1 AND a.man_sync = 1 "
                "ORDER BY a.priority ASC, s.name ASC",
                (account_email,),
            )
        )

        scripts = [{"name": r["name"], "content": r["content"]} for r in rows]

        # Append virtual _spam_blocks script (blocklist → Sieve reject rules)
        virtual = self._spam_blocks_virtual(account_email)
        if virtual:
            scripts.append({"name": "_spam_blocks", "content": virtual["content"]})

        if not scripts:
            return

        combined, _warnings = combine_scripts(scripts)

        is_valid, err = validate_sieve(combined)
        if not is_valid and err:
            import logging

            logging.getLogger(__name__).warning(
                "Combined sieve script validation failed for %s: %s",
                account_email,
                err,
            )
            return

        cfg = self._get_managesieve_config(account_email)
        if not cfg:
            return
        password = self._get_account_password(account_email)
        if not password:
            return

        try:
            mgr = SieveManager(cfg["host"], port=cfg["port"], use_tls=cfg["use_tls"])
            mgr.connect(account_email, password)
            try:
                mgr.put_script("_combined", combined)
                mgr.activate_script("_combined")
            finally:
                mgr.disconnect()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "ManageSieve combine-sync failed for %s", account_email,
            )


__all__ = ["SieveRemoteMixin"]
