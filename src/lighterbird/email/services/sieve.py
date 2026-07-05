"""SieveService — global Sieve script management + per-account activation.

Design:
  - Sieve scripts are **global** (stored once, not per-account).
  - Per-account activation is tracked in ``sieve_activations``.
  - This allows a script to be activated on multiple accounts.
  - Scripts are stored locally in SQLite and backed up like other data.
  - Optional ManageSieve (RFC 5804) remote sync per activation.
  - ``_spam_blocks`` is a virtual system script generated on-the-fly
    from ``SpamManager.to_sieve()`` — it is NOT stored in the DB.

CRUD operations and activation management are provided by
:class:`SieveCrudMixin` (``sieve_crud``). Remote ManageSieve sync is
provided by :class:`SieveRemoteMixin` (``sieve_remote``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lighterbird.email.services.sieve_crud import SieveCrudMixin
from lighterbird.email.services.sieve_remote import SieveRemoteMixin


class SieveService(SieveCrudMixin, SieveRemoteMixin):
    """Manage global Sieve scripts with per-account activation."""

    SYSTEM_PREFIX = "_"

    def __init__(self, db) -> None:
        self.db = db

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _validate_name(self, name: str) -> None:
        """Reject names reserved for system scripts."""
        if name.startswith(self.SYSTEM_PREFIX):
            raise ValueError(
                f"Script name '{name}' starts with '{self.SYSTEM_PREFIX}' "
                f"which is reserved for system scripts."
            )

    # ── Spam blocks (virtual script) ─────────────────────────────────────

    def _spam_blocks_virtual(self, account_email: str) -> dict[str, Any] | None:
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

    # ── Spam block integration ───────────────────────────────────────────

    def upsert_spam_blocks(self, account_email: str, content: str) -> dict[str, Any]:
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
                "created_at": row.get("akt_created_at", ""),
                "modified_at": row.get("akt_updated_at", ""),
            }
        return {
            "name": row["name"],
            "content": row.get("content", ""),
            "system": bool(row.get("system", 0)),
            "created_at": row.get("created_at", ""),
            "modified_at": row.get("updated_at", ""),
            "aktivado": akt,
        }


__all__ = ["SieveService"]
