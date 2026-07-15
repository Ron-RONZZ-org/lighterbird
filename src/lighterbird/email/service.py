"""EmailService — unified facade for email operations.

Composes AccountService, MessageService, and MessageOpsService.
"""

from __future__ import annotations

import email.parser
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Per-account IMAP connection lock ───────────────────────────────────
#
# Prevents concurrent IMAP connections for the same account.  Multiple
# paths can open IMAP connections independently:
#
#   * ``EmailSyncWorker._do_sync()``    (background worker thread)
#   * ``EmailSyncWorker._do_process_trash()``  (background worker thread)
#   * ``POST /api/v1/sync/start``       (dedicated thread, not the worker)
#   * ``!sync`` command handler          (request thread, synchronous)
#   * ``POST /api/v1/email/trash/clear`` (request thread)
#
# Without coordination these concurrent connections can race on the same
# IMAP folder (one thread scanning UIDs while another EXPUNGEs), causing
# missed or duplicated messages.
#
# The ``_account_imap_locks`` dict provides a ``threading.Lock`` per
# account email.  Code that opens an IMAP connection for an account MUST
# call ``acquire_account_imap_lock(email)`` before connecting and
# ``release_account_imap_lock(email)`` after disconnecting.
#
# Lock acquisition has a 30-second timeout.  If the lock cannot be
# acquired, the caller should skip the IMAP operation gracefully and
# log a warning rather than block indefinitely.

_account_imap_locks: dict[str, threading.Lock] = {}
_account_imap_locks_lock = threading.Lock()


def acquire_account_imap_lock(account_email: str, timeout: float = 30.0) -> bool:
    """Acquire the per-account IMAP lock for *account_email*.

    Returns True if the lock was acquired, False on timeout.

    Creating the lock lazily on first access avoids memory for accounts
    that never have IMAP operations.
    """
    global _account_imap_locks
    with _account_imap_locks_lock:
        if account_email not in _account_imap_locks:
            _account_imap_locks[account_email] = threading.Lock()
        lock = _account_imap_locks[account_email]
    acquired = lock.acquire(timeout=timeout)
    if not acquired:
        logger.warning(
            "[imap_lock] Could not acquire IMAP lock for %s within %.1fs timeout — "
            "another IMAP operation is in progress for this account",
            account_email, timeout,
        )
    return acquired


def release_account_imap_lock(account_email: str) -> None:
    """Release the per-account IMAP lock for *account_email*."""
    global _account_imap_locks
    with _account_imap_locks_lock:
        lock = _account_imap_locks.get(account_email)
    if lock:
        try:
            lock.release()
        except RuntimeError:
            pass  # Lock not held by this thread — ignore


from lighterbird.core.drafts import save_draft
from lighterbird.email.db import get_db
from lighterbird.email.imap.connpool import IMAPConnectionPool
from lighterbird.email.services import (
    AccountService,
    MessageOpsService,
    MessageService,
    SieveService,
    SignatureService,
)
from lighterbird.email.sync.folder_mapper import FolderMapper


class EmailService:
    """Unified email operations facade."""

    def __init__(self, db=None):
        self._db = db or get_db()
        self.accounts = AccountService(self._db)
        self.messages = MessageService(self._db)
        self.msg_ops = MessageOpsService(self._db, self.accounts)
        self.sieve = SieveService(self._db)
        self.signatures = SignatureService(self._db)
        self.imap_pool = IMAPConnectionPool()
        self.folder_mapper = FolderMapper(self._db)

    # ── Account operations ───────────────────────────────────────────────

    def create_account(self, data: dict, password: str) -> dict:
        return self.accounts.create_account(data, password)

    def list_accounts(self):
        return self.accounts.list_accounts()

    def delete_account(self, email: str):
        """Delete an account and its keyring password.

        DB deletion first (cascades to messages, attachments), then
        keyring — prevents password orphan if DB fails.
        Follows pattern from A-lien's ``RetpostoAccountsMixin.delete_account``.
        """
        result = self.accounts.delete(email)
        if result:
            self.accounts.delete_password(email)
        return result

    def get_account(self, email: str):
        return self.accounts.get_account_with_password(email)

    def resolve_account(self, identifier: str):
        return self.accounts.resolve_account(identifier)

    # ── Sync ─────────────────────────────────────────────────────────────

    def sync_account(self, email: str, force: bool = False,
                     progress_tracker=None, task_id: str | None = None,
                     manage_progress: bool = True,
                     folder_offset: int = 0,
                     folders: list[str] | None = None,
                     folders_only: bool = False):
        """Sync messages for a single account by email.

        Always returns a SyncResult (never raises).  Before connecting
        to IMAP, all pending backlog entries for this account are drained
        (expunge, trash, flag sync) so the server reflects all local
        operations before the IMAP scan — preventing re-import of
        hard-deleted messages and ensuring flag state consistency.

        If *progress_tracker* and *task_id* are provided, folder-level
        progress is reported via ``progress_tracker.update_folder()``.
        When *manage_progress* is True (default), the tracker is also
        configured with the folder count and marked complete at the end.
        *folder_offset* is the global starting index for folder progress;
        used by ``sync_all`` for a smooth 0–100% progress bar across
        multiple accounts.

        Args:
            folders: If provided, only sync these folder(s).
            folders_only: If True, only register folder hierarchy
                (no message bodies, no trash processing, no draft sync).
        """
        from lighterbird.email.imap import sync_account as _sync
        from lighterbird.email.imap.sync import SyncResult

        result = SyncResult()
        acct = self.accounts.get_account_with_password(email)
        if not acct:
            result.errors.append(f"Account not found: {email}")
        elif not acct.get("password"):
            result.errors.append(
                f"No password configured for account {email}. "
                f"Set it with: !email account modify {email} --password <pw>"
            )
        else:
            # Step 1: Drain pending backlog entries for this account BEFORE
            # acquiring the IMAP sync lock.  This ensures all local operations
            # (hard-delete, soft-delete, flag changes) are reflected on the
            # server before we scan it, preventing re-import of deleted messages
            # and ensuring flag state consistency.
            # The BacklogService acquires its own per-account IMAP lock internally,
            # so there is no lock ordering concern with the sync lock below.
            # If the backlog lock is busy (another thread is processing), this is
            # best-effort — the sync proceeds without draining, and the backlog
            # entries will be retried on the next cycle.
            pending = self.msg_ops.backlog.count_pending(account_email=email)
            if pending:
                drained = self.msg_ops.backlog.process_all(account_email=email)
                logger.info(
                    "Drained %d/%d backlog entries before IMAP sync for %s",
                    drained, pending, email,
                )

            # Step 2: Acquire per-account IMAP lock for the sync scan.
            if not acquire_account_imap_lock(email):
                result.errors.append(
                    f"IMAP operation already in progress for {email}. "
                    "Sync skipped — pending backlog entries were drained "
                    "and will be retried on the next cycle."
                )
            else:
                try:
                    result = _sync(
                        host=acct.get("imap_server", ""),
                        port=acct.get("imap_port", 993),
                        use_ssl=acct.get("imap_use_ssl", 1) == 1,
                        username=acct.get("imap_username", "") or acct.get("email", ""),
                        password=acct["password"],
                        account_email=email,
                        db_store=self,
                        folders=folders,
                        force=force,
                        progress_tracker=progress_tracker,
                        task_id=task_id,
                        manage_progress=manage_progress,
                        folder_offset=folder_offset,
                        folder_mapper=self.folder_mapper,
                        folders_only=folders_only,
                    )
                except ConnectionError as e:
                    result = SyncResult()
                    result.errors.append(str(e))
                except Exception as e:
                    result = SyncResult()
                    result.errors.append(f"Sync error: {e}")
                finally:
                    release_account_imap_lock(email)
        # Note: No post-sync backlog drain here.  The pre-sync drain above
        # already processed all entries that existed before the sync started.
        # Any entries enqueued during sync (e.g. user flag toggles during
        # the sync window) will be picked up by the background worker or
        # the next sync cycle.
        return result

    def sync_all(self, force: bool = False,
                 progress_tracker=None, task_id: str | None = None) -> dict[str, dict]:
        """Sync messages for all accounts.

        When *progress_tracker* is provided, progress is reported at the
        folder level using a global folder counter across all accounts,
        so the progress bar moves smoothly from 0% to 100%.
        """
        accounts = self.accounts.list_accounts()

        # Count total folders across all accounts for a smooth progress bar
        total_folder_count = 0
        if progress_tracker is not None and task_id:
            for acct in accounts:
                rows = self.db.execute(
                    "SELECT COUNT(*) AS cnt FROM folders WHERE account_email = ?",
                    (acct["email"],),
                )
                total_folder_count += rows[0]["cnt"] if rows else 0
            progress_tracker.set_total_folders(task_id, total_folder_count)

        results = {}
        folder_offset = 0
        for acct in accounts:
            email = acct["email"]
            try:
                sr = self.sync_account(
                    email, force=force,
                    progress_tracker=progress_tracker,
                    task_id=task_id,
                    manage_progress=False,
                    folder_offset=folder_offset,
                )
                results[email] = sr.to_dict()
                # Advance offset by the number of folders for this account
                rows = self.db.execute(
                    "SELECT COUNT(*) AS cnt FROM folders WHERE account_email = ?",
                    (email,),
                )
                folder_offset += rows[0]["cnt"] if rows else 0
            except Exception as e:
                results[email] = {"total": 0, "new": 0, "errors": [str(e)]}
        return results

    # ── Message queries ──────────────────────────────────────────────────

    def get_message(self, uuid_: str):
        return self.messages.get_message(uuid_)

    def list_messages(self, account_email=None, folder=None, limit=50, offset=0, sort="newest"):
        return self.messages.list_messages(
            account_email=account_email, folder=folder, limit=limit, offset=offset, sort=sort
        )

    def search_messages(self, filters: dict, limit=50):
        return self.messages.search_messages(filters, limit=limit)

    def search_remote(
        self, account_email: str, query: str,
        folder: str | None = None,
        criteria: dict[str, str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Server-side IMAP text search, returns matched messages.

        When the local DB has header-only messages (``body_fetched=0``),
        body text search via SQL ``LIKE`` returns no results.  This method
        delegates the full-text search to the IMAP server via ``UID SEARCH
        TEXT``, then cross-references the returned UIDs with the local DB.

        Args:
            account_email: Account to search.
            query: Free-text search string.
            folder: Optional folder to scope the search.
            criteria: Optional structured filters (from_, subject, after, before).

        Returns:
            List of message dicts (same format as ``search_messages``).
        """
        acct = self.accounts.get_account_with_password(account_email)
        if not acct or not acct.get("password"):
            return []

        from lighterbird.email.imap.client import IMAPClient

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

            all_uids: set[int] = set()
            target_folders = [folder] if folder else [
                r["name"] for r in self.db.execute(
                    "SELECT name FROM folders WHERE account_email = ? ORDER BY sync_priority, name",
                    (account_email,),
                )
            ]

            for fname in target_folders:
                uids = client.search_remote(fname, query, criteria=criteria)
                all_uids.update(uids)
                if len(all_uids) >= limit:
                    break

            if not all_uids:
                return []

            # Cross-reference with local DB
            uid_list = sorted(all_uids)[:limit]
            placeholders = ",".join("?" for _ in uid_list)
            rows = self.db.execute(
                "SELECT * FROM messages WHERE account_email = ? "
                f"AND imap_uid IN ({placeholders}) AND is_deleted = 0 "
                "ORDER BY received_at DESC LIMIT ?",
                (account_email, *uid_list, limit),
            )
            return list(rows)
        except Exception:
            logger = __import__("logging").getLogger(__name__)
            logger.warning(
                "search_remote: IMAP search failed for %s", account_email,
                exc_info=True,
            )
            return []
        finally:
            client.disconnect()

    def export_eml(self, uuid_: str) -> str | None:
        """Export a message as .eml (RFC 822) string."""
        return self.messages.export_eml(uuid_)

    def import_eml(self, path: str) -> dict[str, Any]:
        """Import a .eml file and save it as an email draft.

        Returns the created draft dict.
        """
        eml_path = Path(path)
        if not eml_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(eml_path, "rb") as f:
            parsed = email.parser.BytesParser().parse(f)

        subject = parsed.get("Subject", "(imported)")
        from_addr = parsed.get("From", "")
        to_addr = parsed.get("To", "")
        body = ""
        if parsed.is_multipart():
            for part in parsed.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
                    break
        else:
            payload = parsed.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")

        draft_data = {
            "subject": subject,
            "from_addr": from_addr,
            "to_addr": to_addr,
            "body": body,
        }
        draft = save_draft(domain="email", title=subject, data=draft_data)
        return draft

    def get_conversation(self, uuid_: str, limit: int = 20) -> list[dict[str, Any]]:
        msg = self.get_message(uuid_)
        if not msg:
            return []
        return self.messages.find_conversation(
            message_id=msg.get("message_id", ""),
            references=msg.get("references", ""),
            in_reply_to=msg.get("in_reply_to", ""),
            limit=limit,
        )

    def process_sync_backlog(self) -> int:
        """Process pending IMAP flag syncs."""
        return self.msg_ops.process_sync_backlog()

    @property
    def backlog_service(self) -> Any:
        """Access the BacklogService for manual operations."""
        return self.msg_ops.backlog

    @property
    def dead_letter_service(self) -> Any:
        """Access the DeadLetterService for management."""
        return self.msg_ops.dead_letter

    # ── Message operations ───────────────────────────────────────────────


    # ── Per-account IMAP lock (convenience wrappers) ───────────────────────

    def acquire_imap_lock(self, account_email: str, timeout: float = 30.0) -> bool:
        """Acquire the per-account IMAP lock for *account_email*.

        Returns True if the lock was acquired, False on timeout.
        """
        return acquire_account_imap_lock(account_email, timeout=timeout)

    def release_imap_lock(self, account_email: str) -> None:
        """Release the per-account IMAP lock for *account_email*."""
        release_account_imap_lock(account_email)

    def mark_read(self, msg_uuid: str, is_read: bool = True):
        self.msg_ops.mark_read(msg_uuid, is_read)

    def trash_message(self, msg_uuid: str):
        self.msg_ops.trash_message(msg_uuid)

    def move_message(self, msg_uuid: str, destination_folder_name: str):
        self.msg_ops.move_message(msg_uuid, destination_folder_name)

    def send_email(self, account_email: str, to: list[str], subject: str,
                   body: str = "", cc: list[str] | None = None,
                   bcc: list[str] | None = None, priority: int = 3,
                   body_format: str = "markdown",
                   attachments: list[dict[str, Any]] | None = None,
                   signature: str | None = None,
                   signature_format: str = "plain",
                   in_reply_to: str | None = None,
                   save_as_sample: bool = True) -> dict:
        return self.msg_ops.send_email(account_email, to, subject, body, cc=cc,
                                       bcc=bcc, priority=priority,
                                       body_format=body_format,
                                       attachments=attachments,
                                       signature=signature,
                                       signature_format=signature_format,
                                       in_reply_to=in_reply_to,
                                       save_as_sample=save_as_sample)

    def save_draft_to_imap(self, draft: dict[str, Any]) -> str | None:
        """Best-effort save of an email draft to the IMAP DRAFTS folder.

        Builds a minimal RFC 2822 message from the draft data and appends
        it to the account's IMAP DRAFTS folder with the ``\\Draft`` flag.

        Uses ``IMAPConnectionPool`` for connection reuse and the per-account
        IMAP lock to avoid races with sync/backlog operations.

        If the same draft UUID already exists in DRAFTS (tracked via
        ``email_draft_uid_map`` table), it is replaced rather than appended
        a second copy.  The ``APPENDUID`` response is parsed to populate
        the UID map on first save, so subsequent saves avoid SEARCH HEADER.

        Returns:
            ``None`` on success, or an error message string on failure.
        """
        import uuid as _uuid
        from email.message import EmailMessage

        from lighterbird.email.imap.connpool import IMAPConnectionError

        data = draft.get("data", {})
        account_email = (data or {}).get("account", "")
        draft_uuid = draft.get("uuid", "")

        if not account_email or not draft_uuid:
            msg = "Draft missing account_email or uuid"
            logger.warning("Cannot sync draft to IMAP: %s. Draft: %s", msg, draft)
            return msg

        acct = self.accounts.get_account_with_password(account_email)
        if not acct or not acct.get("password"):
            msg = f"Account {account_email} not found or no password configured"
            logger.warning("Cannot sync draft to IMAP: %s", msg)
            return msg

        to_str = (data or {}).get("to", "")
        subject = (data or {}).get("subject", "") or "(no subject)"
        body = (data or {}).get("body", "")
        cc_str = (data or {}).get("cc", "")
        bcc_str = (data or {}).get("bcc", "")

        sender_email = acct.get("email", "") or acct.get("smtp_username", "")

        # Build a minimal RFC 2822 message for the draft
        msg = EmailMessage()
        msg["From"] = sender_email
        msg["To"] = to_str
        if cc_str:
            msg["Cc"] = cc_str
        if bcc_str:
            msg["Bcc"] = bcc_str
        msg["Subject"] = subject
        msg["Message-ID"] = f"<{_uuid.uuid4()!s}>"
        msg["X-Draft-UUID"] = draft_uuid
        msg["Date"] = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S %z")
        msg.set_content(body or "")

        message_bytes = msg.as_bytes()

        # Acquire per-account IMAP lock before connecting
        if not acquire_account_imap_lock(account_email):
            return (
                f"Draft saved locally but IMAP sync deferred for {account_email} "
                f"— another IMAP operation is in progress. "
                f"The draft will sync on the next save."
            )

        try:
            # Get connection from pool
            try:
                client = self.imap_pool.acquire(
                    account_email=account_email,
                    host=acct.get("imap_server", ""),
                    port=acct.get("imap_port", 993),
                    use_ssl=acct.get("imap_use_ssl", 1) == 1,
                    username=acct.get("imap_username", "") or acct.get("email", ""),
                    password=acct["password"],
                )
            except IMAPConnectionError as exc:
                return f"IMAP connection failed for {account_email}: {exc}"

            # Resolve localized Drafts folder name via FolderMapper
            folder_name = self.folder_mapper.resolve_drafts(account_email)
            client.ensure_folder(account_email, folder_name, self, "\\Drafts")

            # Check UID map for existing IMAP draft with this draft UUID
            existing_row = self._db.execute_one(
                "SELECT imap_uid, folder_name FROM email_draft_uid_map "
                "WHERE account_email = ? AND draft_uuid = ?",
                (account_email, draft_uuid),
            )

            if existing_row and existing_row["imap_uid"] is not None:
                # Known UID — delete by UID (no SEARCH needed)
                uid_bytes = str(existing_row["imap_uid"]).encode()
                client.delete_message_by_uid(existing_row["folder_name"], uid_bytes)
            else:
                # Unknown UID — fall back to SEARCH HEADER
                existing_uids = client.search_by_header(folder_name, "X-Draft-UUID", draft_uuid)
                for uid in existing_uids:
                    client.delete_message_by_uid(folder_name, uid)

            # Append the new draft
            success, imap_uid = client.append_message(folder_name, message_bytes, flags=["\\Draft"])
            if not success:
                return f"IMAP APPEND failed for draft {draft_uuid[:8]} in {folder_name}"

            # Update or insert into UID map
            now = datetime.now(UTC).isoformat()
            self._db.execute(
                "INSERT OR REPLACE INTO email_draft_uid_map "
                "(account_email, folder_name, draft_uuid, imap_uid, message_id, "
                " created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (account_email, folder_name, draft_uuid,
                 imap_uid, msg.get("Message-ID", ""), now, now),
            )

            logger.info(
                "Draft %s synced to IMAP %s for %s (UID=%s)",
                draft_uuid[:8], folder_name, account_email, imap_uid,
            )
            return None
        except Exception as exc:
            err = f"IMAP sync failed for {account_email}: {exc}"
            logger.exception(
                "Failed to sync draft %s to IMAP DRAFTS for %s: %s",
                draft_uuid[:8], account_email, exc,
            )
            return err
        finally:
            self.imap_pool.release(account_email)
            release_account_imap_lock(account_email)

    def process_send_queue(self, limit: int = 50) -> dict:
        """Process pending send-queue entries with exponential backoff.

        Args:
            limit: Maximum number of queue entries to process.

        Returns:
            Dict with ``sent``, ``retrying``, ``failed`` counts.
        """
        return self.msg_ops.process_send_queue(limit=limit)

    # ── MessageStore protocol (used by IMAP sync) ────────────────────────

    # ── Spam block management ──────────────────────────────────────────

    @property
    def spam(self):
        """Get a SpamManager instance for the email DB."""
        from lighterbird.email.filters.spam import SpamManager

        return SpamManager(self._db)

    @property
    def db(self):
        return self._db

    # NOTE: no db setter — changing _db after construction would orphan
    # the sub-service instances (self.accounts, self.messages, etc.)
