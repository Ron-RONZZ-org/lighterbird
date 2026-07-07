"""Folder name resolution service — handles localized folder names.

Maps canonical folder names (Trash, Sent, Junk, etc.) to actual server
folder names using SPECIAL-USE flags discovered during IMAP LIST.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Common localized names for the Trash folder across various IMAP servers.
# Used as fallback when the SPECIAL-USE \\Trash flag is not advertised.
_TRASH_ALIASES: frozenset[str] = frozenset({
    "Trash",
    "Deleted Messages",
    "Deleted",
    "[Gmail]/Papierkorb",
    "[Gmail]/Trash",
    "Papierkorb",
    "Corbeille",
    "Messages supprimées",
    "Eliminati",
    "Eliminados",
    "Papelera",
    "Koschen",
    "Prullenbak",
    "Resiclado",
})

_SENT_ALIASES: frozenset[str] = frozenset({
    "Sent",
    "Sent Messages",
    "Sent Mail",
    "[Gmail]/Sent Mail",
    "Gesendet",
    "Envoyés",
    "Enviados",
    "Posta inviata",
    "Verzonden",
    "Σταλμένα",
})

_JUNK_ALIASES: frozenset[str] = frozenset({
    "Junk",
    "Spam",
    "[Gmail]/Spam",
    "Bulk Mail",
    "Indésirables",
    "Spamverdacht",
    "Correo no deseado",
})


class FolderMapper:
    """Resolve canonical folder names to server-localized names.

    Uses the ``special_use`` column in the ``folders`` table, which is
    populated from IMAP LIST SPECIAL-USE responses.  Falls back to
    known alias lists and ultimately the literal canonical name.
    """

    def __init__(self, db: Any):
        self.db = db

    def resolve_trash(self, account_email: str) -> str:
        """Resolve the Trash folder name for an account.

        Priority:
        1. Folder with special_use='\\\\Trash' in DB
        2. Alias match from _TRASH_ALIASES
        3. Literal 'Trash'

        Args:
            account_email: The account to look up.

        Returns:
            The server-localized Trash folder name.
        """
        return self._resolve_special(account_email, "\\Trash", _TRASH_ALIASES, "Trash")

    def resolve_sent(self, account_email: str) -> str:
        """Resolve the Sent folder name (same priority scheme)."""
        return self._resolve_special(account_email, "\\Sent", _SENT_ALIASES, "Sent")

    def resolve_junk(self, account_email: str) -> str:
        """Resolve the Junk/Spam folder name (same priority scheme)."""
        return self._resolve_special(account_email, "\\Junk", _JUNK_ALIASES, "Junk")

    def _resolve_special(
        self, account_email: str,
        special_use_flag: str,
        aliases: frozenset[str],
        fallback: str,
    ) -> str:
        """Resolve a canonical folder name using SPECIAL-USE, aliases, or fallback."""
        # 1. Check DB for folder with this special_use flag
        row = self.db.execute_one(
            "SELECT name FROM folders "
            "WHERE account_email = ? AND special_use = ? "
            "LIMIT 1",
            (account_email, special_use_flag),
        )
        if row:
            return row["name"]

        # 2. Check aliases among existing folders for this account
        for alias in aliases:
            row = self.db.execute_one(
                "SELECT name FROM folders "
                "WHERE account_email = ? AND name = ? "
                "LIMIT 1",
                (account_email, alias),
            )
            if row:
                return row["name"]

        # 3. Fall back to the canonical name
        return fallback

    def detect_stale_folder(self, account_email: str, folder_name: str) -> bool:
        """Check if a folder still exists for the account.

        Args:
            account_email: The account to check.
            folder_name: The folder name to verify.

        Returns:
            True if the folder does NOT exist (stale), False if it exists.
        """
        row = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM folders "
            "WHERE account_email = ? AND name = ?",
            (account_email, folder_name),
        )
        return (row["cnt"] if row else 0) == 0


__all__ = ["FolderMapper"]
