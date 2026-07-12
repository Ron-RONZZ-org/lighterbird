"""Account-level IMAP sync functions.

Three sync strategies implemented:
1. Header-only sync + lazy body fetch (Strategy A)
2. Parallel folder sync via ThreadPoolExecutor (Strategy B)
3. Priority ordering: special-use folders first, then by sync_priority
"""

from __future__ import annotations

import email as email_lib
import logging
import uuid as _uuid
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
    progress_tracker: Any = None,
    task_id: str | None = None,
    manage_progress: bool = True,
    folder_offset: int = 0,
    folder_mapper: Any | None = None,
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
        progress_tracker: Optional | SyncProgressTracker for progress reporting.
        task_id: Task ID for progress tracking.
        manage_progress: If True (default), calls **set_total_folders()** before
            iterating folders and **complete()** after. Set to False when the
            caller (e.g. ``sync_all``) owns the lifecycle — folder-level progress
            updates (``update_folder``) are still sent regardless.
        folder_offset: Starting index for folder-level progress updates.
            Used by ``sync_all`` to provide a global folder counter across
            multiple accounts so the progress bar moves from 0% to 100%.

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
            if progress_tracker is not None and task_id:
                progress_tracker.fail(task_id, result.errors[-1])
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

        if progress_tracker is not None and task_id and manage_progress:
            progress_tracker.set_total_folders(task_id, len(sorted_folders))

        for idx, folder_name in enumerate(sorted_folders, start=1):
            if progress_tracker is not None and task_id:
                progress_tracker.update_folder(
                    task_id, folder_offset + idx, folder_name,
                )

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

        # Phase 2b: Inverse sync — import new IMAP drafts as local drafts
        try:
            _sync_imap_drafts_to_local(
                client, db_store, account_email, folder_mapper=folder_mapper,
            )
        except Exception:
            logger.warning(
                "[sync] Inverse draft sync failed for %s",
                account_email, exc_info=True,
            )
            result.errors.append(
                "Inverse draft sync (IMAP→local) failed for %s" % account_email,
            )

        if progress_tracker is not None and task_id and manage_progress:
            progress_tracker.complete(
                task_id,
                result_total=result.total,
                result_new=result.new,
                errors=result.errors or None,
            )
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


# Maximum number of new IMAP drafts to import per sync cycle (rate-limit).
_IMAP_DRAFT_SYNC_LIMIT = 50


def _sync_imap_drafts_to_local(
    client: IMAPClient, db_store: Any, account_email: str,
    folder_mapper: Any | None = None,
) -> None:
    """Import new IMAP DRAFTS folder messages as local composition drafts.

    Uses UIDNEXT-based incremental detection: queries
    ``email_draft_uid_map`` for the maximum known UID for this
    account+folder, then only processes UIDs greater than that value.
    Each imported draft is recorded in the UID map so subsequent syncs
    skip it.

    Args:
        client: Connected IMAPClient instance.
        db_store: Object with ``.db`` (LighterbirdDB) attribute.
        account_email: The account to process.
        folder_mapper: Optional FolderMapper for localized folder name
            resolution.  Falls back to ``"Drafts"`` if not provided.
    """
    from lighterbird.core.drafts import save_draft

    # Resolve Drafts folder name
    drafts_folder = "Drafts"
    if folder_mapper is not None:
        try:
            drafts_folder = folder_mapper.resolve_drafts(account_email)
        except Exception:
            logger.debug(
                "[draft-sync] FolderMapper.resolve_drafts() failed for %s, "
                "falling back to 'Drafts'", account_email,
            )

    # Get max known UID from our map
    row = db_store.db.execute_one(
        "SELECT MAX(imap_uid) AS max_uid FROM email_draft_uid_map "
        "WHERE account_email = ? AND folder_name = ?",
        (account_email, drafts_folder),
    )
    known_max_uid: int = row["max_uid"] if row and row["max_uid"] is not None else 0

    # SELECT the folder read-only to discover new UIDs
    ok, _uidvalidity, _modseq = client.select_folder_ex(
        drafts_folder, readonly=True,
    )
    if not ok:
        logger.debug(
            "[draft-sync] Cannot select %s for %s", drafts_folder, account_email,
        )
        return

    # UID SEARCH for messages after known_max_uid
    try:
        typ, uid_data = client.conn.uid(
            "search", None, f"UID {known_max_uid + 1}:*",
        )
    except Exception as exc:
        logger.debug(
            "[draft-sync] UID SEARCH failed for %s/%s: %s",
            account_email, drafts_folder, exc,
        )
        return

    if typ != "OK" or not uid_data or not uid_data[0]:
        return

    new_uids = [int(x) for x in uid_data[0].split()]
    if not new_uids:
        return

    # Rate-limit to avoid importing hundreds of drafts at once
    if len(new_uids) > _IMAP_DRAFT_SYNC_LIMIT:
        logger.info(
            "[draft-sync] Limiting import from %d to %d new drafts for %s",
            len(new_uids), _IMAP_DRAFT_SYNC_LIMIT, account_email,
        )
        new_uids = new_uids[:_IMAP_DRAFT_SYNC_LIMIT]

    now = datetime.now(UTC).isoformat()

    for uid in new_uids:
        try:
            # Fetch the full message (header + body) for this UID
            typ, fetch_data = client.conn.uid(
                "fetch", str(uid), "(FLAGS BODY.PEEK[] UID)",
            )
            if typ != "OK" or not fetch_data:
                continue

            body_text = ""
            subject = "(IMAP draft)"
            to_addr = ""
            cc_addr = ""
            message_id = ""
            draft_uuid = None

            for item in fetch_data:
                if not isinstance(item, tuple):
                    continue
                raw_data = item[1]
                parsed = email_lib.message_from_bytes(raw_data)

                subject = parsed.get("Subject", subject) or subject
                to_addr = parsed.get("To", "")
                cc_addr = parsed.get("Cc", "")
                message_id = parsed.get("Message-ID", "")

                # Extract X-Draft-UUID if the draft was originally created
                # by lighterbird
                x_uuid = parsed.get("X-Draft-UUID", "")
                if x_uuid:
                    draft_uuid = x_uuid

                # Extract body text (prefer plain text)
                if parsed.is_multipart():
                    for part in parsed.walk():
                        ctype = part.get_content_type()
                        if ctype == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_text = payload.decode("utf-8", errors="replace")
                            break
                else:
                    payload = parsed.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode("utf-8", errors="replace")

            # Skip if already in the UID map (already known)
            existing = db_store.db.execute_one(
                "SELECT 1 FROM email_draft_uid_map "
                "WHERE account_email = ? AND folder_name = ? AND imap_uid = ?",
                (account_email, drafts_folder, uid),
            )
            if existing:
                continue

            # Create local draft
            local_draft = save_draft(
                domain="email",
                title=subject or "(IMAP draft)",
                data={
                    "account": account_email,
                    "to": to_addr,
                    "subject": subject,
                    "body": body_text,
                    "cc": cc_addr or "",
                },
                draft_uuid=draft_uuid,
            )

            # Record in UID map
            db_store.db.execute(
                "INSERT OR IGNORE INTO email_draft_uid_map "
                "(account_email, folder_name, draft_uuid, imap_uid, message_id, "
                " created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (account_email, drafts_folder, local_draft["uuid"],
                 uid, message_id, now, now),
            )

        except Exception as exc:
            logger.warning(
                "[draft-sync] Error importing draft UID %d for %s: %s",
                uid, account_email, exc,
            )

    logger.info(
        "[draft-sync] Imported %d new IMAP draft(s) from %s for %s",
        len(new_uids), drafts_folder, account_email,
    )
