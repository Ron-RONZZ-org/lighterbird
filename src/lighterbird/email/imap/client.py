"""IMAP client wrapper — connection, folder listing, sync.

Forked from A-lien's imap/client.py, stripped of i18n.
"""

from __future__ import annotations

import email as email_lib
import imaplib
import logging
import re
import socket
import ssl
import uuid as uuid_mod
from datetime import UTC, datetime
from typing import Any

from lighterbird.core.storage import AttachmentStore
from lighterbird.email.imap.capabilities import IMAPCapabilities, detect_capabilities
from lighterbird.email.imap.parser import parse_email_message
from lighterbird.email.imap.storage import store_message, _insert_message

logger = logging.getLogger(__name__)

# Chunk sizes that suggest the IMAP server truncated results.
# If a UID SEARCH returns exactly this many UIDs, we assume there
# might be more and query again from the next UID onward.
_UID_CHUNK_THRESHOLDS = (5000, 10000, 20000)

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


# Regex for RFC 3501 LIST response: (flags) SP delimiter SP mailbox-name
# Matches:  (flags) "delimiter" "mailbox"  or  (flags) delimiter mailbox
_LIST_RE = re.compile(
    rb'\(([^)]*)\)\s+'
    rb'(?:"([^"]*)"|(\S+))\s+'
    rb'(?:"([^"]*)"|(\S+))',
)

# Regex to extract UID from FETCH response
_IMAP_UID_RE = re.compile(rb"UID (\d+)")


def _imap_quote_folder(name: str) -> str:
    """Quote a folder name for use in IMAP commands.

    Python 3.13's imaplib does not always quote folder names containing
    special characters (``&``, spaces) in ``_simple_command``, causing
    SELECT/EXAMINE to fail.  This helper ensures the name is quoted.
    """
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _to_imap_date(iso_date: str) -> str:
    """Convert ISO date (``YYYY-MM-DD``) to IMAP date format (``DD-Mon-YYYY``).

    IMAP SEARCH uses ``SINCE 1-Jan-2024`` not ``SINCE 2024-01-01``.
    Returns the original string if parsing fails.
    """
    import datetime
    try:
        dt = datetime.datetime.strptime(iso_date, "%Y-%m-%d").date()
        return dt.strftime("%d-%b-%Y")
    except (ValueError, TypeError):
        return iso_date


def _parse_list_response(line: bytes) -> dict[str, Any] | None:
    """Parse a single IMAP LIST response line.

    Uses a primary regex that follows RFC 3501 ``mailbox-list`` grammar,
    with a fallback parser for non-standard responses (inspired by
    A-lien's IMAP client).  Returns dict with ``name``, ``delimiter``,
    ``flags``, ``special_use``, or ``None`` if the line cannot be parsed.

    The fallback handles cases where the regex fails:
    - Server returns extra response codes after the mailbox name
    - Folder name sent as a literal (not quoted)
    - Non-standard IMAP implementations
    """
    if not line:
        return None

    name = ""
    delimiter = "/"
    flat_flags: list[str] = []

    # Strategy 1: primary regex
    match = _LIST_RE.search(line)
    if match:
        raw_flags = match.group(1)
        raw_delim = match.group(2) if match.group(2) is not None else match.group(3)
        raw_name = match.group(4) if match.group(4) is not None else match.group(5)

        delimiter = raw_delim.decode("utf-8", errors="replace")
        name = raw_name.decode("utf-8", errors="replace")
        flat_flags = [
            f.decode("utf-8", errors="replace")
            for f in raw_flags.split() if f
        ]
    else:
        # Strategy 2: fallback — split on double quotes, extract name as
        # the last quoted segment.  This handles LIST responses where the
        # regex fails (e.g. extended formats, literal names).
        decoded = line.decode("utf-8", errors="replace")
        parts = decoded.split('"')

        # Find the last non-empty quoted segment as the name.
        # Skip candidates that look like delimiters (/ or . or NIL).
        for i in range(len(parts) - 1, 0, -1):
            candidate = parts[i].strip()
            if not candidate:
                continue
            # Skip delimiter-like candidates (single char, or NIL)
            if candidate in ("/", ".", "NIL", "nil"):
                continue
            # Skip flag-like candidates (start with \ or ()
            if candidate.startswith(("\\", "(")):
                continue
            name = candidate
            if i >= 2:
                delim_part = parts[i - 1].strip()
                if delim_part and delim_part not in ("NIL", "nil"):
                    delimiter = delim_part
            break

        # Extract flags from the first parenthesized group
        open_paren = decoded.find("(")
        close_paren = decoded.find(")", open_paren + 1) if open_paren >= 0 else -1
        if 0 <= open_paren < close_paren:
            raw_str = decoded[open_paren + 1:close_paren]
            flat_flags = [f.strip() for f in raw_str.split() if f.strip()]

        if not name:
            logger.warning(
                "Fallback LIST parse also failed: %r", line[:200],
            )
            return None

        logger.debug(
            "Fallback LIST parser used for line (regex did not match): %r "
            "→ name=%r delimiter=%r flags=%r",
            line[:200], name, delimiter, flat_flags,
        )

    if not name:
        return None

    # Detect SPECIAL-USE (case-insensitive matching)
    special_use = None
    for flag in flat_flags:
        upper_flag = flag.upper().lstrip("\\")
        for key, val in _SPECIAL_USE_MAP.items():
            if key.upper().lstrip("\\") == upper_flag:
                special_use = val
                break
        if special_use:
            break

    return {
        "name": name,
        "delimiter": delimiter or "/",
        "flags": flat_flags,
        "special_use": special_use,
    }


class IMAPClient:
    """Low-level IMAP operations for a single connection."""

    def __init__(self, host: str, port: int = 993, use_ssl: bool = True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self._conn: imaplib.IMAP4 | None = None
        self.capabilities: IMAPCapabilities = IMAPCapabilities()

    def connect(self, username: str, password: str) -> None:
        """Connect and login to IMAP server.

        After successful login, detects server capabilities.
        """
        try:
            if self.use_ssl:
                self._conn = imaplib.IMAP4_SSL(self.host, self.port, timeout=30)
            else:
                self._conn = imaplib.IMAP4(self.host, self.port, timeout=30)
            self._conn.login(username, password)
            self.capabilities = detect_capabilities(self._conn)
        except imaplib.IMAP4.error as e:
            raise ConnectionError(f"IMAP authentication failed for {username} at {self.host}:{self.port} — {e}") from e
        except (socket.gaierror, ConnectionRefusedError, TimeoutError, ssl.SSLError, OSError) as e:
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
            logger.warning(
                "list_folders: IMAP LIST returned typ=%r with %d line(s)",
                typ, len(data) if data else 0,
            )
            return result
        skipped = 0
        for line in data:
            parsed = _parse_list_response(line)
            if parsed:
                result.append(parsed)
            else:
                skipped += 1
        if skipped:
            logger.warning(
                "list_folders: parsed %d folder(s), skipped %d unparseable line(s)",
                len(result), skipped,
            )
        else:
            logger.info(
                "list_folders: parsed %d folder(s)", len(result),
            )
        return result

    def ensure_folder(self, account_email: str, folder_name: str,
                      db_store: Any, special_use: str | None = None) -> str:
        """Ensure folder exists in local DB, return its name.

        Uses ``(account_email, name)`` as the natural key (INSERT OR IGNORE).
        If ``special_use`` is provided, updates the ``special_use`` column
        on INSERT OR IGNORE.

        Args:
            account_email: The account this folder belongs to.
            folder_name: The server folder name.
            db_store: Object with ``.db`` (LighterbirdDB) attribute.
            special_use: Optional SPECIAL-USE flag (e.g. ``\\Trash``).

        Returns:
            The folder name.
        """
        now = datetime.now(UTC).isoformat()
        try:
            if special_use:
                db_store.db.execute(
                    "INSERT OR IGNORE INTO folders "
                    "(account_email, name, special_use, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (account_email, folder_name, special_use, now, now),
                )
            else:
                db_store.db.execute(
                    "INSERT OR IGNORE INTO folders "
                    "(account_email, name, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (account_email, folder_name, now, now),
                )
        except Exception as exc:
            logger.warning(
                "Failed to ensure folder %r for %s: %s",
                folder_name, account_email, exc,
            )
        return folder_name

    def create_folder(self, folder_name: str) -> bool:
        """Create a new IMAP folder/mailbox on the server.

        Sends ``CREATE`` command via imaplib.

        Returns:
            True if the folder was created successfully.
        """
        typ, _data = self.conn.create(folder_name)
        return typ == "OK"

    def rename_folder(self, old_name: str, new_name: str) -> bool:
        """Rename (or move) an IMAP folder on the server.

        IMAP ``RENAME`` changes the folder name, which effectively moves
        the folder in the hierarchy when the new name contains different
        path segments.  All child folders are also moved.

        Args:
            old_name: Current folder name (full IMAP path).
            new_name: New folder name (full IMAP path).

        Returns:
            True if the rename succeeded.
        """
        typ, _data = self.conn.rename(
            _imap_quote_folder(old_name),
            _imap_quote_folder(new_name),
        )
        return typ == "OK"

    def delete_folder(self, folder_name: str) -> bool:
        """Delete an IMAP folder on the server.

        Sends ``DELETE`` command via imaplib.  The folder must be empty
        (no messages) for most IMAP servers.

        Args:
            folder_name: The folder name (full IMAP path) to delete.

        Returns:
            True if the delete succeeded.
        """
        typ, _data = self.conn.delete(_imap_quote_folder(folder_name))
        return typ == "OK"

    # Regex to extract APPENDUID from APPEND response
    # Format: OK [APPENDUID <uidvalidity> <uid>] APPEND completed
    _APPENDUID_RE = re.compile(rb"\[APPENDUID (\d+) (\d+)\]")

    def append_message(self, folder: str, message: bytes,
                       flags: list[str] | None = None) -> tuple[bool, int | None]:
        """Append a message to an IMAP folder.

        Uses ``imaplib.IMAP4.append()``.  The *message* must be a
        valid RFC 2822 byte string.  Optional *flags* (e.g. ``["\\Draft"]``)
        are set on the appended message.

        Args:
            folder: Target folder name (e.g. ``"Drafts"``).
            message: RFC 2822 message bytes.
            flags: Optional list of IMAP flag strings (e.g. ``["\\Seen"]``).
                   Note that backslashes must be escaped in Python string
                   literals.

        Returns:
            Tuple of (success, imap_uid).  *imap_uid* is the UID assigned
            by the server (from APPENDUID response code), or ``None`` if
            the server did not return an APPENDUID.
        """
        flag_str = " ".join(flags) if flags else ""
        # Pass the datetime object directly — Python 3.13+ imaplib.append()
        # no longer accepts string date_time values and calls
        # Time2Internaldate internally for datetime/struct_time types.
        now = datetime.now(UTC)
        try:
            typ, data = self.conn.append(
                _imap_quote_folder(folder),
                flag_str,
                now,
                message,
            )
            if typ != "OK":
                logger.warning(
                    "IMAP APPEND to %r returned typ=%r", folder, typ,
                )
                return False, None

            # Parse APPENDUID from response (RFC 3502)
            imap_uid: int | None = None
            if data:
                for resp_line in data:
                    if isinstance(resp_line, bytes):
                        m = self._APPENDUID_RE.search(resp_line)
                        if m:
                            imap_uid = int(m.group(2))
                            break

            return True, imap_uid
        except imaplib.IMAP4.error as e:
            logger.warning("IMAP APPEND failed for folder %r: %s", folder, e)
            return False, None

    def search_by_header(self, folder: str, header_name: str,
                         header_value: str) -> list[bytes]:
        """Search for messages in a folder by a header value.

        Uses ``UID SEARCH HEADER <name> <value>``.

        Args:
            folder: Folder to search in.
            header_name: Header name (e.g. ``"X-Draft-UUID"``).
            header_value: Value to match.

        Returns:
            List of matching UIDs as bytes (empty if none).
        """
        try:
            self._select_folder(folder)
            typ, data = self.conn.uid("SEARCH", "HEADER", header_name, header_value)
            if typ != "OK" or not data or not data[0]:
                return []
            return data[0].split()
        except Exception as e:
            logger.warning("IMAP SEARCH for header %r failed: %s", header_name, e)
            return []

    def delete_message_by_uid(self, folder: str, uid: bytes) -> bool:
        """Delete a message by UID using STORE +EXPUNGE.

        Args:
            folder: Folder name.
            uid: UID of the message to delete (as returned by ``UID SEARCH``).

        Returns:
            True if the message was deleted.
        """
        try:
            self._select_folder(folder)
            # STORE +FLAGS.SILENT (\\Deleted)
            typ, _data = self.conn.uid("STORE", uid, "+FLAGS.SILENT", "(\\Deleted)")
            if typ != "OK":
                return False
            # EXPUNGE to permanently remove
            self.conn.expunge()
            return True
        except Exception as e:
            logger.warning("IMAP delete by UID failed for %r: %s", uid, e)
            return False

    # ── Folder selection ───────────────────────────────────────────────

    def _select_folder(self, folder: str) -> bool:
        """Select a folder for write operations. Returns True on success."""
        typ, data = self.conn.select(_imap_quote_folder(folder), readonly=False)
        return typ == "OK"

    def select_folder_ex(self, folder: str, readonly: bool = True,
                         condstore: bool = False) -> tuple[bool, int | None, int | None]:
        """Select a folder and return UIDVALIDITY and HIGHESTMODSEQ.

        Parses the SELECT response for ``[UIDVALIDITY N]`` and
        ``[HIGHESTMODSEQ M]`` response codes (RFC 3501, RFC 4551).

        Args:
            folder: Folder name to select.
            readonly: If True, SELECT with readonly=True (no write lock).
            condstore: If True, enables CONDSTORE on this SELECT
                       (RFC 4551).  Server must advertise CONDSTORE.

        Returns:
            Tuple of (success, uidvalidity, highest_modseq).
            Values may be None if not advertised by the server.
        """
        try:
            # Build SELECT command with optional CONDSTORE parameter.
            # Quote folder name explicitly — Python 3.13's imaplib does
            # not always quote names with special chars (&, spaces).
            quoted = _imap_quote_folder(folder)
            if condstore and self.capabilities.has_condstore:
                typ, data = self.conn._simple_command(
                    "SELECT", quoted, b"(CONDSTORE)"
                )
            else:
                typ, data = self.conn.select(quoted, readonly=readonly)

            if typ != "OK":
                return False, None, None

            uidvalidity: int | None = None
            highest_modseq: int | None = None

            # Parse response for UIDVALIDITY and HIGHESTMODSEQ
            untagged = data or []
            for resp in untagged:
                if isinstance(resp, bytes):
                    resp_str = resp.decode("ascii", errors="replace")
                else:
                    continue

                # Match UIDVALIDITY N
                if "UIDVALIDITY" in resp_str:
                    import re
                    m = re.search(r"UIDVALIDITY\s+(\d+)", resp_str)
                    if m:
                        uidvalidity = int(m.group(1))

                # Match HIGHESTMODSEQ N
                if "HIGHESTMODSEQ" in resp_str:
                    import re
                    m = re.search(r"HIGHESTMODSEQ\s+(\d+)", resp_str)
                    if m:
                        highest_modseq = int(m.group(1))

            return True, uidvalidity, highest_modseq
        except Exception:
            logger.warning("select_folder_ex failed for %r", folder, exc_info=True)
            return False, None, None

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
        db_store: Any, force: bool = False, headers_only: bool = False,
    ) -> dict[str, Any]:
        """Sync messages in a single folder.

        Uses IMAP UID SEARCH/FETCH for stable dedup, with ``Message-ID``
        as the cross-folder stable identifier.

        When *headers_only* is True (default for initial sync), fetches only
        ``BODY.PEEK[HEADER]`` — no body text or attachments. Messages are
        marked ``body_fetched=0`` and bodies are fetched lazily on read.
        This makes the first sync dramatically faster (minutes → seconds).

        Args:
            folder: IMAP folder name.
            account_email: Account email.
            folder_name: Local folder name (may differ from IMAP folder).
            db_store: Object with .db (LighterbirdDB).
            force: If True, re-download all messages.
            headers_only: If True, fetch only headers (lazy body).

        Returns:
            Dict with keys: total, new, errors.
        """
        result: dict[str, Any] = {"total": 0, "new": 0, "errors": []}
        try:
            typ, data = self.conn.select(_imap_quote_folder(folder), readonly=True)
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
                if len(chunk) in _UID_CHUNK_THRESHOLDS:
                    search_uid_from = chunk[-1] + 1
                else:
                    break

            result["total"] = len(all_uids)
            known_uids: set[int] = set()
            if not force:
                rows = db_store.db.execute(
                    "SELECT imap_uid FROM messages WHERE account_email = ? AND folder_name = ? AND imap_uid IS NOT NULL",
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

            # Choose FETCH items based on mode
            fetch_items = "(FLAGS BODY.PEEK[HEADER] UID RFC822.SIZE)" if headers_only else "(FLAGS BODY.PEEK[] UID)"

            for start in range(0, len(new_uids), 100):
                chunk = new_uids[start:start + 100]
                uid_list = b",".join(str(u).encode() for u in chunk)
                typ, fetch_data = self.conn.uid("fetch", uid_list, fetch_items)
                if typ != "OK" or not fetch_data:
                    result["errors"].append(f"FETCH error at IDs {chunk[0]}..{chunk[-1]}")
                    continue
                pending_attachments: list[tuple[str, str, bytes]] = []
                for item in fetch_data:
                    if not isinstance(item, tuple):
                        logger.debug(
                            "sync_folder: non-tuple item in FETCH response: %r",
                            item[:200] if isinstance(item, bytes) else type(item).__name__,
                        )
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
                        msg = email_lib.message_from_bytes(raw_data)
                        data = parse_email_message(
                            msg, account_email, folder_name, imap_uid,
                            store_attachments=not headers_only,
                        )
                        if headers_only:
                            data["body_fetched"] = 0
                        msg_uuid = store_message(db_store.db, data, force=force, account_email=account_email, folder_name=folder_name)
                        # Queue attachment blobs (only when storing full messages)
                        if not headers_only and "_attachments_data" in data:
                            for att in data["_attachments_data"]:
                                pending_attachments.append((msg_uuid, att["content_id"], att["data"]))
                        # Store attachment metadata (only when storing full messages)
                        if not headers_only and "_attachments_meta" in data:
                            now_ts = datetime.now(UTC).isoformat()
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
                # Batch-flush attachment blobs after each chunk
                if pending_attachments:
                    store = AttachmentStore()
                    for msg_uuid, content_id, blob_data in pending_attachments:
                        try:
                            store.store(msg_uuid, content_id, blob_data)
                        except Exception as store_err:
                            result["errors"].append(
                                f"Attachment store error for UID batch: {store_err}"
                            )
            self.conn.close()
        except Exception as e:
            result["errors"].append(f"Sync error: {e}")
        return result

    def fetch_message_body(
        self, account_email: str, folder_name: str,
        imap_uid: int, db_store: Any,
    ) -> dict[str, Any] | None:
        """Lazy-fetch full message body + attachments for a header-only message.

        Connects to the IMAP server, selects the folder, fetches the full
        message body (``BODY.PEEK[]``), parses it, and updates the local DB
        row.  After this call the message has ``body_fetched=1`` and its
        ``body``, ``html_body``, and attachments are available.

        Args:
            account_email: Account email.
            folder_name: Folder name.
            imap_uid: IMAP UID of the message.
            db_store: Object with ``.db`` (LighterbirdDB).

        Returns:
            The updated message dict, or ``None`` on failure.
        """
        try:
            # Must SELECT the folder first before fetching
            typ, _ = self.conn.select(_imap_quote_folder(folder_name), readonly=True)
            if typ != "OK":
                logger.warning(
                    "fetch_message_body: cannot select %s/%s",
                    account_email, folder_name,
                )
                return None
            typ, fetch_data = self.conn.uid(
                "fetch", str(imap_uid), "(FLAGS BODY.PEEK[] UID)",
            )
            if typ != "OK" or not fetch_data:
                logger.warning(
                    "fetch_message_body: FETCH failed for UID %s in %s/%s",
                    imap_uid, account_email, folder_name,
                )
                return None

            for item in fetch_data:
                if not isinstance(item, tuple):
                    continue
                raw_data = item[1]
                msg = email_lib.message_from_bytes(raw_data)
                data = parse_email_message(
                    msg, account_email, folder_name, imap_uid,
                    store_attachments=True,
                )
                data["body_fetched"] = 1

                # Update the existing DB row
                now_ts = datetime.now(UTC).isoformat()
                db_store.db.execute(
                    "UPDATE messages SET body = ?, html_body = ?, "
                    "body_fetched = 1, updated_at = ? WHERE account_email = ? "
                    "AND folder_name = ? AND imap_uid = ?",
                    (
                        data.get("body", ""), data.get("html_body", ""),
                        now_ts, account_email, folder_name, imap_uid,
                    ),
                )

                # Store attachment blobs
                if "_attachments_data" in data:
                    store = AttachmentStore()
                    for att in data["_attachments_data"]:
                        try:
                            store.store(data["uuid"], att["content_id"], att["data"])
                        except Exception:
                            pass

                # Insert attachment metadata
                if "_attachments_meta" in data:
                    for meta in data["_attachments_meta"]:
                        try:
                            att_uuid = str(uuid_mod.uuid4())
                            store_path = f"{data['uuid']}/{meta['content_id']}"
                            db_store.db.execute(
                                "INSERT OR IGNORE INTO email_attachments "
                                "(uuid, message_uuid, filename, mime_type, size, content_id, storage_path, created_at, updated_at) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (att_uuid, data["uuid"], meta["filename"],
                                 meta["mime_type"], meta["size"],
                                 meta["content_id"], store_path,
                                 now_ts, now_ts),
                            )
                        except Exception:
                            pass

                return data
        except Exception as exc:
            logger.warning(
                "fetch_message_body: error for UID %s in %s/%s: %s",
                imap_uid, account_email, folder_name, exc,
            )
            return None

    def search_remote(
        self, folder: str, query: str,
        criteria: dict[str, str] | None = None,
    ) -> list[int]:
        """Server-side IMAP SEARCH, returns matching UIDs.

        Delegates body text search to the IMAP server using ``UID SEARCH
        TEXT`` / ``UID SEARCH SUBJECT`` / etc.  This is essential for
        header-only synced messages whose body is not stored locally.

        Args:
            folder: Folder to search in (e.g. ``"INBOX"``).
            query: Free-text search string.
            criteria: Optional dict with structured filters:
                - ``from_``: sender pattern
                - ``subject``: subject pattern
                - ``after``: date string (YYYY-MM-DD)
                - ``before``: date string (YYYY-MM-DD)

        Returns:
            List of IMAP UIDs matching the search.

        Raises:
            ConnectionError: If the IMAP connection fails.
        """
        try:
            self.conn.select(_imap_quote_folder(folder), readonly=True)
        except Exception as exc:
            raise ConnectionError(
                f"Cannot select folder {folder!r} for search: {exc}"
            ) from exc

        # Build IMAP SEARCH criteria
        parts: list[str] = []

        if criteria:
            from_str = criteria.get("from_", "")
            if from_str:
                parts.append(f'FROM "{from_str}"')
            to_str = criteria.get("to", "")
            if to_str:
                parts.append(f'TO "{to_str}"')
            cc_str = criteria.get("cc", "")
            if cc_str:
                parts.append(f'CC "{cc_str}"')
            subj = criteria.get("subject", "")
            if subj:
                parts.append(f'SUBJECT "{subj}"')
            # participant = OR( FROM, TO, CC ) — searches all sender/recipient fields
            participant_str = criteria.get("participant", "")
            if participant_str:
                parts.append(
                    f'OR FROM "{participant_str}" '
                    f'OR TO "{participant_str}" '
                    f'CC "{participant_str}"'
                )
            after = criteria.get("after", "")
            if after:
                parts.append(f'SINCE {_to_imap_date(after)}')
            before = criteria.get("before", "")
            if before:
                parts.append(f'BEFORE {_to_imap_date(before)}')

        if query:
            parts.append(f'TEXT "{query}"')

        if not parts:
            return []

        search_cmd = " ".join(parts)

        try:
            typ, data = self.conn.uid("search", None, search_cmd)
        except Exception as exc:
            logger.warning(
                "search_remote: UID SEARCH failed in %r: %s",
                folder, exc,
            )
            return []

        if typ != "OK" or not data or not data[0]:
            return []

        return [int(uid) for uid in data[0].split()]

# store_message and _insert_message moved to storage.py