"""IMAP client wrapper — connection, folder listing, sync.

Forked from A-lien's imap/client.py, stripped of i18n.
"""

from __future__ import annotations

import email as email_lib
import imaplib
import re
import socket
import ssl
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Any


_SPECIAL_USE_MAP = {
    "\\Inbox": "INBOX",
    "\\Sent": "Sent",
    "\\Trash": "Trash",
    "\\Drafts": "Drafts",
    "\\Junk": "Junk",
    "\\Spam": "Spam",
    "\\Archive": "Archive",
    "\\All": "All Mail",
    "\\Flagged": "Starred",
}


def _parse_list_response(line: bytes) -> dict[str, Any] | None:
    """Parse a single IMAP LIST response line.

    Returns dict with ``name``, ``delimiter``, ``flags``, or None.
    """
    if not line:
        return None
    # RFC 3501: (flags) "/" "name"
    parts = line.split(b'"')
    flags_str = b""
    delimiter = "/"
    name = ""

    if len(parts) >= 1:
        # Flags are before the first quoted delimiter, in parentheses
        raw = parts[0]
        paren_idx = raw.find(b"(")
        if paren_idx >= 0:
            end_idx = raw.find(b")", paren_idx)
            if end_idx >= 0:
                flags_str = raw[paren_idx + 1 : end_idx]

    if len(parts) >= 3:
        delimiter = parts[1].decode("utf-8", errors="replace")
        name = parts[2].strip().strip(b'"').strip()
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
    elif len(parts) >= 2:
        name = parts[-2].strip().strip(b'"').strip()
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")

    if not name:
        return None

    flags = [
        f.decode("utf-8", errors="replace")
        for f in flags_str.split() if f
    ]

    # Detect SPECIAL-USE
    special_use = None
    for flag in flags:
        upper_flag = flag.upper()
        if upper_flag in _SPECIAL_USE_MAP:
            special_use = _SPECIAL_USE_MAP[upper_flag]
            break

    return {
        "name": name,
        "delimiter": delimiter or "/",
        "flags": flags,
        "special_use": special_use,
    }


class IMAPClient:
    """Low-level IMAP operations for a single connection."""

    def __init__(self, host: str, port: int = 993, use_ssl: bool = True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self._conn: imaplib.IMAP4 | None = None

    def connect(self, username: str, password: str) -> None:
        """Connect and login to IMAP server."""
        try:
            if self.use_ssl:
                self._conn = imaplib.IMAP4_SSL(self.host, self.port, timeout=30)
            else:
                self._conn = imaplib.IMAP4(self.host, self.port, timeout=30)
            self._conn.login(username, password)
        except imaplib.IMAP4.error as e:
            raise ConnectionError(f"IMAP authentication failed for {username} at {self.host}:{self.port} — {e}") from e
        except (socket.gaierror, ConnectionRefusedError,
                TimeoutError, socket.timeout, ssl.SSLError, OSError) as e:
            raise ConnectionError(f"IMAP connection failed: {username} at {self.host}:{self.port} — {e}") from e
        except Exception as e:
            raise ConnectionError(f"IMAP connection failed: {username} at {self.host}:{self.port} — {e}") from e

    @property
    def conn(self) -> imaplib.IMAP4:
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._conn

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def list_folders(self) -> list[dict[str, Any]]:
        """List all IMAP folders/mailboxes with SPECIAL-USE flags."""
        result: list[dict[str, Any]] = []
        typ, data = self.conn.list()
        if typ != "OK" or not data:
            return result
        for line in data:
            parsed = _parse_list_response(line)
            if parsed:
                result.append(parsed)

        # Assign canonical names for standard folders not already named
        for folder in result:
            if folder["special_use"] and folder["name"] != folder["special_use"]:
                # Keep the server name but tag with special_use hint
                pass
        return result

    def ensure_folder(self, account_email: str, folder_name: str, db_store: Any) -> str:
        """Ensure folder exists in local DB, return its name.

        Uses ``(account_email, name)`` as the natural key (INSERT OR IGNORE).
        """
        now = datetime.now(timezone.utc).isoformat()
        try:
            db_store.db.execute(
                "INSERT OR IGNORE INTO folders "
                "(account_email, name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (account_email, folder_name, now, now),
            )
        except Exception:
            pass
        return folder_name

    def create_folder(self, folder_name: str) -> bool:
        """Create a new IMAP folder/mailbox on the server.

        Sends ``CREATE`` command via imaplib.

        Returns:
            True if the folder was created successfully.
        """
        typ, _data = self.conn.create(folder_name)
        return typ == "OK"

    # ── Write operations (move, copy, delete) ──────────────────────────

    def _select_folder(self, folder: str) -> bool:
        """Select a folder for write operations. Returns True on success."""
        typ, data = self.conn.select(folder, readonly=False)
        return typ == "OK"

    def copy_message(self, uid: int, from_folder: str, to_folder: str) -> bool:
        """Copy a message from *from_folder* to *to_folder* via IMAP UID COPY.

        Requires folder to be selected (select is done internally).
        Returns True on success, False on failure.
        """
        if not self._select_folder(from_folder):
            return False
        typ, data = self.conn.uid("COPY", str(uid), to_folder)
        return typ == "OK"

    def move_message(self, uid: int, from_folder: str, to_folder: str) -> bool:
        """Move a message from *from_folder* to *to_folder* via IMAP UID MOVE.

        Falls back to COPY + STORE + EXPUNGE if MOVE (RFC 6851) is not
        supported by the server.
        Returns True on success, False on failure.
        """
        if not self._select_folder(from_folder):
            return False
        try:
            typ, data = self.conn.uid("MOVE", str(uid), to_folder)
            if typ == "OK":
                return True
        except imaplib.IMAP4.error:
            pass
        # Fallback: COPY + STORE \Deleted + EXPUNGE
        typ, data = self.conn.uid("COPY", str(uid), to_folder)
        if typ != "OK":
            return False
        try:
            self.conn.uid("STORE", str(uid), "+FLAGS", "(\\Deleted)")
            self.conn.expunge()
        except imaplib.IMAP4.error:
            return False
        return True

    def delete_message(self, uid: int, folder: str) -> bool:
        """Mark a message as deleted and expunge it from *folder*.

        Returns True on success, False on failure.
        """
        if not self._select_folder(folder):
            return False
        try:
            typ, data = self.conn.uid("STORE", str(uid), "+FLAGS", "(\\Deleted)")
            if typ != "OK":
                return False
            self.conn.expunge()
            return True
        except imaplib.IMAP4.error:
            return False

    def set_flags(
        self, uid: int, folder: str,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> bool:
        """Add or remove IMAP flags on a message by UID.

        Args:
            uid: IMAP UID of the message.
            folder: Folder name to select.
            add: List of flags to add (e.g. ``["\\Seen"]``).
            remove: List of flags to remove.

        Returns:
            True on success, False on failure.
        """
        if not self._select_folder(folder):
            return False
        try:
            if add:
                flag_str = " ".join(add)
                typ, _ = self.conn.uid("STORE", str(uid), "+FLAGS.SILENT", f"({flag_str})")
                if typ != "OK":
                    return False
            if remove:
                flag_str = " ".join(remove)
                typ, _ = self.conn.uid("STORE", str(uid), "-FLAGS.SILENT", f"({flag_str})")
                if typ != "OK":
                    return False
            return True
        except imaplib.IMAP4.error:
            return False

    def sync_folder(
        self, folder: str, account_email: str, folder_name: str,
        db_store: Any, force: bool = False,
    ) -> dict[str, Any]:
        """Sync messages in a single folder.

        Uses IMAP UID SEARCH/FETCH for stable dedup, with ``Message-ID``
        as the cross-folder stable identifier.

        Returns:
            Dict with keys: total, new, errors.
        """
        result: dict[str, Any] = {"total": 0, "new": 0, "errors": []}
        try:
            typ, data = self.conn.select(folder, readonly=True)
            if typ != "OK":
                result["errors"].append(f"Cannot select folder: {folder}")
                return result

            all_uids: list[int] = []
            search_uid_from: int | None = None
            while True:
                if search_uid_from is not None:
                    typ, uid_data = self.conn.uid("search", None, f"UID {search_uid_from}:*")
                else:
                    typ, uid_data = self.conn.uid("search", None, "ALL")
                if typ != "OK" or not uid_data or not uid_data[0]:
                    break
                chunk = [int(x) for x in uid_data[0].split()]
                if not chunk:
                    break
                all_uids.extend(chunk)
                if len(chunk) in (5000, 10000, 20000):
                    search_uid_from = chunk[-1] + 1
                else:
                    break

            result["total"] = len(all_uids)
            known_uids: set[int] = set()
            if not force:
                rows = db_store.db.execute(
                    "SELECT imap_uid FROM messages WHERE account_email = ? AND folder_name = ? AND imap_uid IS NOT NULL AND is_deleted = 0",
                    (account_email, folder_name),
                )
                known_uids = {r["imap_uid"] for r in rows}
            else:
                known_uids = set()

            new_uids = [uid for uid in all_uids if uid not in known_uids]
            if not new_uids:
                self.conn.close()
                return result

            new_uids.sort(reverse=True)
            _IMAP_UID_RE = re.compile(rb"UID (\d+)")

            for start in range(0, len(new_uids), 100):
                chunk = new_uids[start:start + 100]
                uid_list = b",".join(str(u).encode() for u in chunk)
                typ, fetch_data = self.conn.uid("fetch", uid_list, "(FLAGS BODY.PEEK[] UID)")
                if typ != "OK" or not fetch_data:
                    result["errors"].append(f"FETCH error at IDs {chunk[0]}..{chunk[-1]}")
                    continue
                for item in fetch_data:
                    if not isinstance(item, tuple):
                        continue
                    raw_flags = item[0] if item[0] else b""
                    raw_data = item[1]
                    imap_uid = -1
                    try:
                        uid_match = _IMAP_UID_RE.search(raw_flags)
                        if not uid_match:
                            result["errors"].append(
                                f"UID regex failed on: {raw_flags[:200]!r}"
                            )
                            continue
                        imap_uid = int(uid_match.group(1))
                        if not force and imap_uid in known_uids:
                            continue
                        from lighterbird.email.imap.parser import parse_email_message
                        from lighterbird.core.storage import AttachmentStore
                        msg = email_lib.message_from_bytes(raw_data)
                        data = parse_email_message(msg, account_email, folder_name, imap_uid, store_attachments=True)
                        # Insert or update message FIRST to get the canonical msg_uuid
                        msg_uuid = store_message(db_store.db, data, force=force, account_email=account_email, folder_name=folder_name)
                        # Store attachment blobs using msg_uuid as directory name
                        if "_attachments_data" in data:
                            store = AttachmentStore()
                            for att in data["_attachments_data"]:
                                try:
                                    store.store(msg_uuid, att["content_id"], att["data"])
                                except Exception as store_err:
                                    result["errors"].append(
                                        f"Attachment store error for UID {imap_uid}: {store_err}"
                                    )
                        # Store attachment metadata in email_attachments table
                        if "_attachments_meta" in data:
                            now_ts = datetime.now(timezone.utc).isoformat()
                            for meta in data["_attachments_meta"]:
                                try:
                                    att_uuid = str(uuid_mod.uuid4())
                                    store_path = f"{msg_uuid}/{meta['content_id']}"
                                    db_store.db.execute(
                                        "INSERT OR IGNORE INTO email_attachments "
                                        "(uuid, message_uuid, filename, mime_type, size, content_id, storage_path, created_at, updated_at) "
                                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                        (att_uuid, msg_uuid, meta["filename"], meta["mime_type"],
                                         meta["size"], meta["content_id"], store_path,
                                         now_ts, now_ts),
                                    )
                                except Exception as meta_err:
                                    result["errors"].append(
                                        f"Attachment meta insert error for UID {imap_uid}: {meta_err}"
                                    )
                        result["new"] += 1
                    except Exception as e:
                        result["errors"].append(f"Parse/store error at UID {imap_uid}: {e}")
            self.conn.close()
        except Exception as e:
            result["errors"].append(f"Sync error: {e}")
        return result


def store_message(
    db: Any,
    data: dict[str, Any],
    force: bool = False,
    account_email: str | None = None,
    folder_name: str | None = None,
) -> str:
    """Insert or update a message in messages table.

    Uses ``Message-ID`` for cross-folder dedup when available.
    Falls back to creating a new UUID for messages without one.
    """
    msg_uuid = data.get("uuid") or str(uuid_mod.uuid4())
    message_id = data.get("message_id")

    # Try dedup by Message-ID first
    if message_id and account_email:
        existing = db.execute_one(
            "SELECT uuid, is_read, is_starred FROM messages "
            "WHERE account_email = ? AND message_id = ?",
            (account_email, message_id),
        )
        if existing:
            msg_uuid = existing["uuid"]
            if force:
                is_read = existing["is_read"]
                is_starred = existing["is_starred"]
                db.execute("DELETE FROM messages WHERE uuid = ?", (msg_uuid,))
                # Re-insert preserving read/star state
                _insert_message(db, data, msg_uuid, account_email, folder_name)
                db.execute(
                    "UPDATE messages SET is_read = ?, is_starred = ? WHERE uuid = ?",
                    (is_read, is_starred, msg_uuid),
                )
            else:
                # Update folder and UID for existing message
                db.execute(
                    "UPDATE messages SET folder_name = ?, imap_uid = ?, "
                    "updated_at = ? WHERE uuid = ?",
                    (folder_name, data.get("imap_uid"),
                     datetime.now(timezone.utc).isoformat(), msg_uuid),
                )
            return msg_uuid

    # Fall back to UID-based dedup (per-folder)
    imap_uid = data.get("imap_uid")
    if imap_uid is not None and account_email and folder_name:
        existing = db.execute_one(
            "SELECT uuid, is_read, is_starred FROM messages "
            "WHERE account_email = ? AND folder_name = ? AND imap_uid = ?",
            (account_email, folder_name, imap_uid),
        )
        if existing:
            msg_uuid = existing["uuid"]
            if force:
                is_read = existing["is_read"]
                is_starred = existing["is_starred"]
                db.execute("DELETE FROM messages WHERE uuid = ?", (msg_uuid,))
                _insert_message(db, data, msg_uuid, account_email, folder_name)
                db.execute(
                    "UPDATE messages SET is_read = ?, is_starred = ? WHERE uuid = ?",
                    (is_read, is_starred, msg_uuid),
                )
            else:
                return msg_uuid  # Already known

    # Fallback: cross-folder UID dedup — search for the same imap_uid
    # across ALL folders (not just the current one). This catches
    # messages that were moved between folders (e.g., trashed) and
    # re-appear in the original folder during sync. Without this,
    # a duplicate row with is_read=0 would be created, overwriting
    # the user's local read status.
    if imap_uid is not None and account_email:
        existing = db.execute_one(
            "SELECT uuid, is_read, is_starred FROM messages "
            "WHERE account_email = ? AND imap_uid = ?",
            (account_email, imap_uid),
        )
        if existing:
            msg_uuid = existing["uuid"]
            if force:
                is_read = existing["is_read"]
                is_starred = existing["is_starred"]
                db.execute("DELETE FROM messages WHERE uuid = ?", (msg_uuid,))
                _insert_message(db, data, msg_uuid, account_email, folder_name)
                db.execute(
                    "UPDATE messages SET is_read = ?, is_starred = ? WHERE uuid = ?",
                    (is_read, is_starred, msg_uuid),
                )
            else:
                # Update folder, uid, and timestamps for the move
                db.execute(
                    "UPDATE messages SET folder_name = ?, imap_uid = ?, "
                    "updated_at = ? WHERE uuid = ?",
                    (folder_name, imap_uid,
                     datetime.now(timezone.utc).isoformat(), msg_uuid),
                )
            return msg_uuid

    # New message — insert
    _insert_message(db, data, msg_uuid, account_email, folder_name)
    return msg_uuid


def _insert_message(
    db: Any, data: dict[str, Any],
    msg_uuid: str, account_email: str | None, folder_name: str | None,
) -> None:
    """Insert a message row safely.

    Uses INSERT OR IGNORE to prevent silently overwriting existing
    rows (e.g., when the UNIQUE INDEX on
    ``(account_email, folder_name, imap_uid)`` triggers a REPLACE).
    If the insert is ignored (row already exists), the existing data
    — including user flags like ``is_read`` — is preserved.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        db.execute(
            """INSERT INTO messages
               (uuid, account_email, folder_name, message_id, in_reply_to,
                imap_uid, from_addr, to_recipients, cc_recipients,
                subject, body, html_body,
                priority, is_read, is_starred, is_deleted,
                received_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (msg_uuid, account_email or data.get("account_email", ""),
             folder_name or data.get("folder_name"),
             data.get("message_id", ""), data.get("in_reply_to", ""),
             data.get("imap_uid"), data.get("from_addr", ""), data.get("to_recipients", "[]"),
             data.get("cc_recipients", "[]"), data.get("subject", ""), data.get("body", ""),
             data.get("html_body", ""), data.get("priority", 5),
             int(data.get("is_read", 0)), int(data.get("is_starred", 0)),
             int(data.get("is_deleted", 0)), data.get("received_at", ""),
             data.get("created_at", ""), data.get("updated_at", "")),
        )
    except Exception as exc:
        # Row already exists (UUID or UNIQUE INDEX conflict).
        # Preserve existing data — this is a safety net in case
        # store_message's dedup logic missed a duplicate.
        logger.warning(
            "_insert_message skipped for %s (%s): %s",
            msg_uuid[:8], data.get("imap_uid"), exc,
        )
