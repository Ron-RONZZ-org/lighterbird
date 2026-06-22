"""Account-level IMAP sync functions.

Forked from A-lien's imap/sync.py, simplified for MVP.
"""

from __future__ import annotations

import uuid as uuid_mod
from typing import Any

from lighterbird.email.imap.client import IMAPClient


class SyncResult:
    """Result of an IMAP sync operation."""

    def __init__(self):
        self.total = 0
        self.new = 0
        self.errors: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {"total": self.total, "new": self.new, "errors": self.errors}


def sync_account(
    host: str, port: int, use_ssl: bool,
    username: str, password: str,
    konto_id: str,
    db_store: Any,
    folders: list[str] | None = None,
    force: bool = False,
) -> SyncResult:
    """Sync messages from an IMAP account.

    Args:
        host: IMAP server
        port: IMAP port
        use_ssl: Use SSL
        username: Login username
        password: Login password
        konto_id: Account UUID
        db_store: Object with .db (LighterbirdDB)
        folders: Specific folders to sync (None = sync all discovered)
        force: If True, re-download all messages

    Returns:
        SyncResult with counts.
    """
    client = IMAPClient(host, port, use_ssl)
    try:
        client.connect(username, password)
        result = SyncResult()
        available = client.list_folders()
        target_folders = folders or [f["name"] for f in available]

        for folder_name in target_folders:
            dosierujo_id = str(uuid_mod.uuid5(
                uuid_mod.NAMESPACE_DNS, f"{konto_id}/{folder_name}",
            ))
            client.ensure_folder(konto_id, folder_name, db_store)
            fr = client.sync_folder(folder_name, konto_id, dosierujo_id, db_store, force=force)
            result.total += fr["total"]
            result.new += fr["new"]
            result.errors.extend(fr["errors"])
        return result
    finally:
        client.disconnect()
