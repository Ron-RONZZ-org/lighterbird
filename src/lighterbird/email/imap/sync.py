"""Account-level IMAP sync functions.

Updated for Phases 1-3 of the IMAP sync overhaul:
- UIDVALIDITY checking on folder SELECT
- CONDSTORE-based flag pull for server-side changes
- Folder special_use tracking
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lighterbird.email.imap.client import IMAPClient

_SELECT_READONLY = True


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

    Supports CONDSTORE (RFC 4551) for efficient flag pull and
    UIDVALIDITY tracking for detecting UID reassignment.

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

        # Build folder metadata map for special_use lookup
        folder_map: dict[str, dict] = {f["name"]: f for f in available}

        for folder_name in target_folders:
            meta = folder_map.get(folder_name, {})
            special_use = meta.get("special_use")

            # Ensure folder in DB with special_use
            client.ensure_folder(account_email, folder_name, db_store,
                                 special_use=special_use)

            # Check UIDVALIDITY
            ok, uidvalidity, highest_modseq = client.select_folder_ex(
                folder_name, readonly=True,
                condstore=client.capabilities.has_condstore,
            )
            if not ok:
                result.errors.append(f"Cannot select folder: {folder_name}")
                continue

            # Handle UIDVALIDITY change → invalidate local UIDs for this folder
            if uidvalidity is not None:
                _check_uidvalidity(db_store.db, account_email, folder_name, uidvalidity)

            # Update highest_modseq in folders table
            if highest_modseq is not None:
                db_store.db.execute(
                    "UPDATE folders SET highest_modseq = ? "
                    "WHERE account_email = ? AND name = ?",
                    (highest_modseq, account_email, folder_name),
                )

            # Sync new messages (existing behavior)
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


def _check_uidvalidity(db: Any, account_email: str,
                       folder_name: str, server_uidvalidity: int) -> None:
    """Check and handle UIDVALIDITY changes.

    If the server reports a different UIDVALIDITY than what we have
    stored, all local UIDs for that folder are stale.  We delete the
    local messages and backlog entries so they will be re-fetched
    on the next sync.

    Args:
        db: Database connection.
        account_email: The account email.
        folder_name: The folder name.
        server_uidvalidity: The UIDVALIDITY value from the server.
    """
    row = db.execute_one(
        "SELECT uidvalidity FROM folders "
        "WHERE account_email = ? AND name = ?",
        (account_email, folder_name),
    )
    stored_uidvalidity = row["uidvalidity"] if row else None

    if stored_uidvalidity is None:
        # First sync — store the UIDVALIDITY
        db.execute(
            "UPDATE folders SET uidvalidity = ? "
            "WHERE account_email = ? AND name = ?",
            (server_uidvalidity, account_email, folder_name),
        )
        return

    if stored_uidvalidity == server_uidvalidity:
        return  # UIDVALIDITY unchanged — all good

    # UIDVALIDITY changed — invalidate all local UIDs for this folder
    logger = __import__("logging").getLogger(__name__)
    logger.warning(
        "[sync] UIDVALIDITY changed for %s/%s: %s → %s. "
        "Invalidating local messages.",
        account_email, folder_name, stored_uidvalidity, server_uidvalidity,
    )

    # Delete local messages for this folder (they will be re-fetched)
    db.execute(
        "DELETE FROM messages WHERE account_email = ? AND folder_name = ?",
        (account_email, folder_name),
    )
    # Delete backlog entries for this folder (UIDs are stale)
    db.execute(
        "DELETE FROM _sync_backlog WHERE account_email = ? AND folder_name = ?",
        (account_email, folder_name),
    )
    # Update stored UIDVALIDITY
    db.execute(
        "UPDATE folders SET uidvalidity = ? "
        "WHERE account_email = ? AND name = ?",
        (server_uidvalidity, account_email, folder_name),
    )


def _retry_pending_trash(client: IMAPClient, db_store: Any, account_email: str) -> None:
    """Find messages that are soft-deleted (is_deleted=1) but still in
    their original folder, and attempt to move them to the IMAP Trash folder.

    Called after each sync pass to catch messages that were trashed while
    offline or when the IMAP connection was unavailable on the first attempt.
    """
    from datetime import datetime

    pending = list(db_store.db.execute(
        "SELECT uuid, imap_uid, folder_name FROM messages "
        "WHERE account_email = ? AND is_deleted = 1 AND folder_name != 'Trash' "
        "AND imap_uid IS NOT NULL",
        (account_email,),
    ))
    if not pending:
        return

    now = datetime.now(UTC).isoformat()
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
