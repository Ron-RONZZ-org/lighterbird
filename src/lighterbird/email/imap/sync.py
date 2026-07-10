"""Account-level IMAP sync functions.

Three sync strategies implemented:
1. Header-only sync + lazy body fetch (Strategy A)
2. Parallel folder sync via ThreadPoolExecutor (Strategy B)
3. Priority ordering: special-use folders first, then by sync_priority
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

from lighterbird.email.imap.client import IMAPClient

_SELECT_READONLY = True

# Folders with these SPECIAL-USE flags get sync_priority = 1
_HIGH_PRIORITY_NAMES = frozenset({
    "INBOX", "Sent", "Trash", "Drafts", "Junk", "Spam", "Archive",
})


class SyncResult:
    """Result of an IMAP sync operation."""

    def __init__(self):
        self.total = 0
        self.new = 0
        self.errors: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {"total": self.total, "new": self.new, "errors": self.errors}


def _default_sync_priority(folder_name: str, special_use: str | None) -> int:
    """Derive a default sync_priority from folder properties.

    Special-use folders (INBOX, Sent, Trash, etc.) get priority 1.
    Everything else gets priority 10.
    """
    if special_use and special_use in _HIGH_PRIORITY_NAMES:
        return 1
    if folder_name.upper() in _HIGH_PRIORITY_NAMES:
        return 1
    return 10


def _set_folder_priority(
    db: Any, account_email: str, folder_name: str, priority: int,
) -> None:
    """Set sync_priority for a folder in the DB."""
    try:
        db.execute(
            "UPDATE folders SET sync_priority = ? "
            "WHERE account_email = ? AND name = ?",
            (priority, account_email, folder_name),
        )
    except Exception:
        pass  # Best-effort: column may not exist yet


def sync_account(
    host: str, port: int, use_ssl: bool,
    username: str, password: str,
    account_email: str,
    db_store: Any,
    folders: list[str] | None = None,
    force: bool = False,
) -> SyncResult:
    """Sync messages from an IMAP account.

    Three strategies for performance:
    - **Priority ordering**: Folders with special-use flags (INBOX, Sent,
      Trash, etc.) are synced before custom folders. The order can be
      customised via the ``sync_priority`` column in the ``folders`` table.
    - **Header-only sync** (Strategy A): The initial pass fetches only
      message headers (``BODY.PEEK[HEADER]``), making the first sync
      dramatically faster. Full message bodies are fetched lazily when
      the user opens a message.
    - **Parallel folders** (Strategy B): Multiple folders are synced
      concurrently via ``ThreadPoolExecutor`` (up to 3 workers).

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

        try:
            available = client.list_folders()
        except Exception:
            logger.warning(
                "[sync] list_folders() failed for %s — no folders discovered",
                account_email, exc_info=True,
            )
            result.errors.append(
                f"Failed to list IMAP folders for {account_email}. "
                f"Sync will retry on next run.",
            )
            return result

        target_folders = folders or [f["name"] for f in available]

        # Build folder metadata map for special_use lookup
        folder_map: dict[str, dict] = {f["name"]: f for f in available}

        # ── Phase 1: Register ALL folders in DB first ──────────────────────
        # This ensures custom folders appear in the folder list immediately,
        # even if the subsequent message-download phase takes a long time.
        for folder_name in target_folders:
            meta = folder_map.get(folder_name, {})
            special_use = meta.get("special_use")
            client.ensure_folder(account_email, folder_name, db_store,
                                 special_use=special_use)
            # Set default sync_priority
            priority = _default_sync_priority(folder_name, special_use)
            _set_folder_priority(db_store.db, account_email, folder_name, priority)

        # ── Phase 2a: Header-only sync (priority-ordered) ─────────────────
        # Because IMAP connections are not thread-safe, we process folders
        # sequentially here.  The speed gain comes from fetching only headers
        # (no body text, no attachments), which is ~100x faster per message.
        sorted_folders = _get_sorted_folders(
            db_store.db, account_email, target_folders,
        )

        logger.info(
            "[sync] Phase 2a: header-only sync for %d folder(s) on %s",
            len(sorted_folders), account_email,
        )

        for folder_name in sorted_folders:
            # CONDSTORE optimization: if server modseq hasn't changed since
            # last sync, skip this folder entirely (no new messages).
            if not force and client.capabilities.has_condstore:
                stored = db_store.db.execute_one(
                    "SELECT highest_modseq FROM folders "
                    "WHERE account_email = ? AND name = ?",
                    (account_email, folder_name),
                )
                if stored and stored["highest_modseq"] > 0:
                    ok, _uidvalidity, server_modseq = client.select_folder_ex(
                        folder_name, readonly=True, condstore=True,
                    )
                    if ok and server_modseq is not None:
                        if server_modseq <= stored["highest_modseq"]:
                            logger.debug(
                                "[sync] Skipping %s/%s (modseq %d unchanged)",
                                account_email, folder_name, server_modseq,
                            )
                            continue  # No new messages — skip entirely
                        # Modseq changed, proceed with sync below
                        uidvalidity = _uidvalidity
                        highest_modseq = server_modseq
                    else:
                        # CONDSTORE SELECT failed — fall through to normal path
                        uidvalidity = None
                        highest_modseq = None
                else:
                    # First sync or no stored modseq — normal path
                    uidvalidity = None
                    highest_modseq = None
            else:
                # No CONDSTORE — normal SELECT
                ok, uidvalidity, highest_modseq = client.select_folder_ex(
                    folder_name, readonly=True,
                    condstore=client.capabilities.has_condstore,
                )
                if not ok:
                    result.errors.append(f"Cannot select folder: {folder_name}")
                    continue

            if uidvalidity is not None:
                try:
                    _check_uidvalidity(db_store.db, account_email, folder_name, uidvalidity)
                except Exception:
                    logger.warning(
                        "[sync] UIDVALIDITY check failed for %s/%s",
                        account_email, folder_name, exc_info=True,
                    )

            if highest_modseq is not None:
                try:
                    db_store.db.execute(
                        "UPDATE folders SET highest_modseq = ? "
                        "WHERE account_email = ? AND name = ?",
                        (highest_modseq, account_email, folder_name),
                    )
                except Exception:
                    logger.warning(
                        "[sync] Failed to update highest_modseq for %s/%s",
                        account_email, folder_name, exc_info=True,
                    )

            fr = client.sync_folder(
                folder_name, account_email,
                folder_name=folder_name,
                db_store=db_store, force=force,
                headers_only=True,
            )
            result.total += fr["total"]
            result.new += fr["new"]
            result.errors.extend(fr["errors"])

        # Retry moving previously soft-deleted messages to IMAP Trash
        _retry_pending_trash(client, db_store, account_email)
        return result
    finally:
        client.disconnect()


def _get_sorted_folders(
    db: Any, account_email: str, folder_names: list[str],
) -> list[str]:
    """Sort folders by sync_priority ASC, then name ASC.

    Queries the DB for stored priorities; defaults to 10 if not set.
    """
    rows = db.execute(
        "SELECT name, sync_priority FROM folders "
        "WHERE account_email = ? AND name IN ({})".format(
            ",".join("?" for _ in folder_names)
        ),
        (account_email, *folder_names),
    )
    prio_map: dict[str, int] = {r["name"]: r["sync_priority"] for r in rows}
    return sorted(
        folder_names,
        key=lambda n: (prio_map.get(n, 10), n),
    )


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
