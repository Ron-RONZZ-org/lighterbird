"""Server-side flag pull — uses CONDSTORE (RFC 4551) to fetch flag changes.

Provides :class:`FlagPuller` which detects server-side flag changes for
already-known messages and merges them into the local database.

Merge semantics:
- If the user has a pending local change in the backlog → user intent wins.
- Otherwise → server wins (last-writer-wins with server as source of truth).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _flags_to_state(flags: list[str]) -> dict[str, int]:
    """Convert IMAP flag list to local DB state dict.

    Args:
        flags: List of IMAP flag strings (e.g. ``['\\Seen', '\\Flagged']``).

    Returns:
        Dict with ``is_read`` and ``is_starred`` integer values.
    """
    return {
        "is_read": 1 if "\\Seen" in flags else 0,
        "is_starred": 1 if "\\Flagged" in flags else 0,
    }


def _merge(server_state: dict[str, int],
           local_state: dict[str, int],
           has_pending_backlog: bool) -> dict[str, int] | None:
    """Merge server flag state into local state.

    If the user has a pending backlog entry for this message, the
    server state is ignored (user intent wins).

    Args:
        server_state: Dict from ``_flags_to_state()``.
        local_state: Current local DB state (from messages row).
        has_pending_backlog: Whether the backlog has an entry for this msg.

    Returns:
        Dict of changes to apply, or None if no changes needed.
    """
    if has_pending_backlog:
        return None  # User intent wins

    changes: dict[str, int] = {}
    for key in ("is_read", "is_starred"):
        sv = server_state.get(key)
        lv = local_state.get(key)
        if sv is not None and sv != lv:
            changes[key] = sv
    return changes or None


class FlagPuller:
    """Pull server-side flag changes for already-known messages.

    Uses CONDSTORE (RFC 4551) ``FETCH (UID FLAGS MODSEQ) (CHANGEDSINCE N)``
    when the server supports it.  Falls back to no-op if CONDSTORE is
    unavailable — server flag changes will not be pulled.
    """

    def __init__(self, db: Any):
        self.db = db

    def pull_changes(self, account_email: str,
                     folders: list[str] | None = None) -> dict[str, int]:
        """Pull server flag changes for specified folders.

        Args:
            account_email: Account to pull changes for.
            folders: Folders to check.  If None, pulls for all folders.

        Returns:
            Dict mapping folder name to count of local updates applied.
        """
        from lighterbird.email.imap.client import IMAPClient

        if folders is None:
            rows = list(self.db.execute(
                "SELECT name FROM folders WHERE account_email = ?",
                (account_email,),
            ))
            folders = [r["name"] for r in rows]

        results: dict[str, int] = {}
        for folder_name in folders:
            count = self.pull_for_folder(account_email, folder_name)
            if count:
                results[folder_name] = count
        return results

    def pull_for_folder(self, account_email: str,
                        folder_name: str,
                        conn: Any | None = None) -> int:
        """Pull and apply server-side flag changes for one folder.

        Args:
            account_email: Account to pull changes for.
            folder_name: Folder to check.
            conn: Optional connected IMAPClient.  If None, creates a
                  temporary connection (not recommended — prefer passing
                  a connection from the pool).

        Returns:
            Number of local messages updated.
        """
        # Get the highest known modseq for this folder
        row = self.db.execute_one(
            "SELECT highest_modseq FROM folders "
            "WHERE account_email = ? AND name = ?",
            (account_email, folder_name),
        )
        if not row or row["highest_modseq"] is None or row["highest_modseq"] == 0:
            return 0  # No CONDSTORE data available yet

        highest_modseq = row["highest_modseq"]

        own_conn = False
        if conn is None:
            own_conn = True
            conn = self._connect_for_account(account_email)

        if conn is None:
            return 0

        try:
            return self._pull_for_folder_connected(
                conn, account_email, folder_name, highest_modseq,
            )
        except Exception:
            logger.warning(
                "[flag_pull] pull failed for %s/%s", account_email, folder_name,
                exc_info=True,
            )
            return 0
        finally:
            if own_conn and conn:
                conn.disconnect()

    def _connect_for_account(self, account_email: str) -> Any | None:
        """Create a temporary IMAPClient for an account."""
        from lighterbird.email.imap.client import IMAPClient
        from lighterbird.email.services.accounts import AccountService

        acct_svc = AccountService(self.db)
        acct = acct_svc.get_account_with_password(account_email)
        if not acct or not acct.get("password"):
            return None

        client = IMAPClient(
            host=acct.get("imap_server", ""),
            port=acct.get("imap_port", 993),
            use_ssl=acct.get("imap_use_ssl", 1) == 1,
        )
        try:
            client.connect(
                username=acct.get("imap_username", "") or account_email,
                password=acct["password"],
            )
            return client
        except Exception:
            logger.warning(
                "[flag_pull] Cannot connect for %s", account_email,
            )
            return None

    def _pull_for_folder_connected(
        self, conn: Any,
        account_email: str, folder_name: str,
        highest_modseq: int,
    ) -> int:
        """Pull flags using a connected IMAPClient."""
        if not conn.capabilities.has_condstore:
            logger.debug(
                "[flag_pull] CONDSTORE not supported for %s, skipping",
                account_email,
            )
            return 0

        # SELECT folder with CONDSTORE
        ok, _uidvalidity, server_modseq = conn.select_folder_ex(
            folder_name, readonly=True, condstore=True,
        )
        if not ok:
            logger.warning("[flag_pull] Cannot select %s/%s", account_email, folder_name)
            return 0

        if server_modseq is not None and server_modseq <= highest_modseq:
            return 0  # No changes since last pull

        # FETCH (UID FLAGS MODSEQ) (CHANGEDSINCE highest_modseq)
        try:
            typ, data = conn.conn.uid(
                "fetch", None,
                f"(UID FLAGS MODSEQ) (CHANGEDSINCE {highest_modseq})",
            )
        except Exception as exc:
            logger.warning("[flag_pull] FETCH CHANGEDSINCE failed: %s", exc)
            return 0

        if typ != "OK" or not data:
            return 0

        updated = 0
        new_max_modseq = highest_modseq

        for item in data:
            if not isinstance(item, tuple):
                continue
            raw_data = item[0] if item[0] else b""

            # Parse UID, FLAGS, MODSEQ from FETCH response
            uid = _extract_uid(raw_data)
            flags = _extract_flags(raw_data)
            modseq = _extract_modseq(raw_data)

            if uid is None or flags is None:
                continue

            if modseq and modseq > new_max_modseq:
                new_max_modseq = modseq

            # Look up local message
            local = self.db.execute_one(
                "SELECT uuid, is_read, is_starred FROM messages "
                "WHERE account_email = ? AND folder_name = ? AND imap_uid = ?",
                (account_email, folder_name, uid),
            )
            if not local:
                continue

            # Check if backlog has pending entry for this message
            backlog_pending = self.db.execute_one(
                "SELECT COUNT(*) AS cnt FROM _sync_backlog "
                "WHERE msg_uuid = ?", (local["uuid"],),
            )
            has_pending = backlog_pending and backlog_pending["cnt"] > 0

            server_state = _flags_to_state(flags)
            local_state = {
                "is_read": local.get("is_read", 0),
                "is_starred": local.get("is_starred", 0),
            }

            changes = _merge(server_state, local_state, has_pending)
            if changes:
                now = datetime.now(UTC).isoformat()
                set_parts = []
                set_values = []
                for key, val in changes.items():
                    set_parts.append(f"{key} = ?")
                    set_values.append(val)
                set_parts.append("modseq = ?")
                set_values.append(modseq)
                set_parts.append("updated_at = ?")
                set_values.append(now)
                set_values.append(local["uuid"])

                self.db.execute(
                    f"UPDATE messages SET {', '.join(set_parts)} WHERE uuid = ?",
                    tuple(set_values),
                )
                updated += 1
            elif modseq:
                # No effective change, but update modseq to avoid re-fetch
                self.db.execute(
                    "UPDATE messages SET modseq = ? WHERE uuid = ?",
                    (modseq, local["uuid"]),
                )

        conn.conn.close()

        # Update highest_modseq
        if new_max_modseq > highest_modseq:
            self.db.execute(
                "UPDATE folders SET highest_modseq = ? "
                "WHERE account_email = ? AND name = ?",
                (new_max_modseq, account_email, folder_name),
            )

        if updated:
            logger.info(
                "[flag_pull] Updated %d messages in %s/%s via CONDSTORE",
                updated, account_email, folder_name,
            )
        return updated


# ── FETCH response parsers ──────────────────────────────────────────────────


def _extract_uid(raw_data: bytes) -> int | None:
    """Extract UID from a FETCH response.

    Looks for ``UID N`` in the response data.
    """
    import re
    m = re.search(rb"UID\s+(\d+)", raw_data)
    return int(m.group(1)) if m else None


def _extract_flags(raw_data: bytes) -> list[str] | None:
    """Extract FLAGS from a FETCH response.

    Looks for ``FLAGS (...)`` in the response data.
    Returns list of flag strings (e.g. ``['\\Seen', '\\Flagged']``).
    """
    import re
    m = re.search(rb"FLAGS\s*\(([^)]*)\)", raw_data)
    if not m:
        return None
    flag_str = m.group(1).decode("ascii", errors="replace")
    return [f.strip() for f in flag_str.split() if f.strip()]


def _extract_modseq(raw_data: bytes) -> int | None:
    """Extract MODSEQ from a FETCH response.

    Looks for ``MODSEQ (N)`` in the response data (RFC 4551 format).
    """
    import re
    m = re.search(rb"MODSEQ\s*\((\d+)\)", raw_data)
    if not m:
        m = re.search(rb"MODSEQ\s+(\d+)", raw_data)
    return int(m.group(1)) if m else None


__all__ = ["FlagPuller", "_flags_to_state", "_merge", "_extract_uid",
           "_extract_flags", "_extract_modseq"]
