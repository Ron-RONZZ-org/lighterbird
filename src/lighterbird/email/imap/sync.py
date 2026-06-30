"""Account-level IMAP sync functions.

Forked from A-lien's imap/sync.py, simplified for MVP.
"""

from __future__ import annotations

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
    account_email: str,
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
        account_email: Account email (primary key)
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
            client.ensure_folder(account_email, folder_name, db_store)
            fr = client.sync_folder(
                folder_name, account_email,
                folder_name=folder_name,
                db_store=db_store, force=force,
            )
            result.total += fr["total"]
            result.new += fr["new"]
            result.errors.extend(fr["errors"])

        # Retry moving previously soft-deleted messages to IMAP Trash
        _retry_pending_trash(client, db_store, account_email)
        return result
    finally:
        client.disconnect()


def _retry_pending_trash(client: IMAPClient, db_store: Any, account_email: str) -> None:
    """Find messages that are soft-deleted (is_deleted=1) but still in
    their original folder, and attempt to move them to the IMAP Trash folder.

    Called after each sync pass to catch messages that were trashed while
    offline or when the IMAP connection was unavailable on the first attempt.
    """
    from datetime import datetime, timezone

    pending = list(db_store.db.execute(
        "SELECT uuid, imap_uid, folder_name FROM messages "
        "WHERE account_email = ? AND is_deleted = 1 AND folder_name != 'Trash' "
        "AND imap_uid IS NOT NULL",
        (account_email,),
    ))
    if not pending:
        return

    now = datetime.now(timezone.utc).isoformat()
    for msg in pending:
        uid = msg["imap_uid"]
        src_folder = msg["folder_name"]
        if uid is None or not src_folder:
            continue
        try:
            if client.move_message(uid, src_folder, "Trash"):
                db_store.db.execute(
                    "UPDATE messages SET folder_name = 'Trash', is_deleted = 0, "
                    "updated_at = ? WHERE uuid = ?",
                    (now, msg["uuid"]),
                )
        except Exception:
            pass  # will retry on next sync
