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
        """List all IMAP folders/mailboxes."""
        result: list[dict[str, Any]] = []
        typ, data = self.conn.list()
        if typ != "OK" or not data:
            return result
        _folder_re = re.compile(rb'"/" "?([^"]+)"?\s*$')
        for line in data:
            if not line:
                continue
            m = _folder_re.search(line)
            if m:
                name = m.group(1).decode("utf-8", errors="replace").strip()
            else:
                decoded = line.decode("utf-8", errors="replace")
                parts = decoded.split('"')
                if len(parts) >= 3:
                    name = parts[2].strip() if len(parts) == 3 else parts[-2].strip()
                else:
                    continue
            if not name or name == "/":
                decoded = line.decode("utf-8", errors="replace")
                flags_str = decoded.split('"')[0].strip("() ")
                if "\\Sent" in flags_str:
                    name = "Sent"
                elif "\\Drafts" in flags_str:
                    name = "Drafts"
                elif "\\Trash" in flags_str:
                    name = "Trash"
                elif "\\Junk" in flags_str:
                    name = "Junk"
                elif "\\Archive" in flags_str:
                    name = "Archive"
                elif "\\Inbox" in flags_str:
                    name = "INBOX"
                else:
                    continue
            result.append({"name": name, "delimiter": "/", "flags": []})
        return result

    def ensure_folder(self, konto_id: str, folder_name: str, db_store: Any) -> str:
        """Ensure folder exists in local DB, return its UUID."""
        dosierujo_id = str(uuid_mod.uuid5(uuid_mod.NAMESPACE_DNS, f"{konto_id}/{folder_name}"))
        try:
            now = datetime.now(timezone.utc).isoformat()
            db_store.db.execute(
                "INSERT OR IGNORE INTO dosierujoj "
                "(uuid, konto_id, nomo, patro_id, kreita_je, modifita_je) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (dosierujo_id, konto_id, folder_name, None, now, now),
            )
        except Exception:
            pass
        return dosierujo_id

    def sync_folder(
        self, folder: str, konto_id: str, dosierujo_id: str,
        db_store: Any, force: bool = False,
    ) -> dict[str, Any]:
        """Sync messages in a single folder.

        Uses IMAP UID SEARCH/FETCH for stable dedup.

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
                    "SELECT imap_uid FROM mesagoj WHERE konto_id = ? AND dosierujo_id = ? AND imap_uid IS NOT NULL AND forigita = 0",
                    (konto_id, dosierujo_id),
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
                        data = parse_email_message(msg, konto_id, dosierujo_id, imap_uid, store_attachments=True)
                        # Store attachment blobs if any
                        if "_attachments_data" in data:
                            uid_str = str(uuid_mod.uuid4())
                            store = AttachmentStore()
                            for att in data["_attachments_data"]:
                                try:
                                    store.store(uid_str, att["content_id"], att["data"])
                                except Exception as store_err:
                                    result["errors"].append(
                                        f"Attachment store error for UID {imap_uid}: {store_err}"
                                    )
                        # Insert message
                        msg_uuid = store_message(db_store.db, data, force=force)
                        # Store attachment metadata in aldonajxoj table
                        if "_attachments_meta" in data:
                            now_ts = datetime.now(timezone.utc).isoformat()
                            for meta in data["_attachments_meta"]:
                                try:
                                    att_uuid = str(uuid_mod.uuid4())
                                    store_path = f"{uid_str}/{meta['content_id']}"
                                    db_store.db.execute(
                                        "INSERT OR IGNORE INTO aldonajxoj "
                                        "(uuid, mesago_uuid, filename, mime_type, size, content_id, storage_path, kreita_je, modifita_je) "
                                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                        (att_uuid, msg_uuid, meta["dosiernomo"], meta["mime_tipo"],
                                         meta["grandeco"], meta["content_id"], store_path,
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


def store_message(db: Any, data: dict[str, Any], force: bool = False) -> str:
    """Insert or update a message in mesagoj table."""
    msg_uuid = data.get("uuid") or str(uuid_mod.uuid4())
    local_legita = None
    local_stelo = None
    if force:
        imap_uid = data.get("imap_uid")
        if imap_uid is not None:
            existing = db.execute_one(
                "SELECT uuid, legita, stelo FROM mesagoj "
                "WHERE konto_id = ? AND dosierujo_id = ? AND imap_uid = ?",
                (data["konto_id"], data["dosierujo_id"], imap_uid),
            )
            if existing:
                msg_uuid = existing["uuid"]
                local_legita = existing["legita"]
                local_stelo = existing["stelo"]
                db.execute("DELETE FROM mesagoj WHERE uuid = ?", (msg_uuid,))
    db.execute(
        """INSERT OR REPLACE INTO mesagoj
           (uuid, konto_id, dosierujo_id, message_id, in_reply_to,
            imap_uid, de, al, kc, subjekto, korpo, html_korpo,
            prioritato, legita, stelo, forigita,
            ricevita_je, kreita_je, modifita_je)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (msg_uuid, data.get("konto_id", ""), data.get("dosierujo_id", "") or None,
         data.get("message_id", ""), data.get("in_reply_to", ""),
         data.get("imap_uid"), data.get("de", ""), data.get("al", "[]"),
         data.get("kc", "[]"), data.get("subjekto", ""), data.get("korpo", ""),
         data.get("html_korpo", ""), data.get("prioritato", 5),
         int(data.get("legita", 0)), int(data.get("stelo", 0)),
         int(data.get("forigita", 0)), data.get("ricevita_je", ""),
         data.get("kreita_je", ""), data.get("modifita_je", "")),
    )
    if force and local_legita is not None:
        db.execute(
            "UPDATE mesagoj SET legita = ?, stelo = ? WHERE uuid = ?",
            (local_legita, local_stelo, msg_uuid),
        )
    return msg_uuid
