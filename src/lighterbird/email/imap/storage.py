"""Message storage — insert/update email messages in the database.

Extracted from :mod:`client` for module size compliance.
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import UTC, datetime
from typing import Any


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
    if message_id is not None and account_email:
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
                # Update folder and UID for existing message.
                # Reset is_deleted — a message found alive on the server
                # in a new folder is not deleted, even if it was previously
                # soft-deleted locally (e.g. trashed from INBOX and now
                # rediscovered in the Trash folder during sync).
                db.execute(
                    "UPDATE messages SET folder_name = ?, imap_uid = ?, "
                    "is_deleted = 0, updated_at = ? WHERE uuid = ?",
                    (folder_name, data.get("imap_uid"),
                     datetime.now(UTC).isoformat(), msg_uuid),
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

    # New message — insert
    _insert_message(db, data, msg_uuid, account_email, folder_name)
    return msg_uuid


def _insert_message(
    db: Any, data: dict[str, Any],
    msg_uuid: str, account_email: str | None, folder_name: str | None,
) -> None:
    """Insert or update a message row.

    Uses ON CONFLICT DO UPDATE instead of INSERT OR REPLACE to avoid
    cascading deletes of email_attachments (which FK REFERENCES messages
    with ON DELETE CASCADE).
    """
    db.execute(
        """INSERT INTO messages
           (uuid, account_email, folder_name, message_id, in_reply_to,
            imap_uid, from_addr, to_recipients, cc_recipients,
            subject, body, html_body,
            priority, is_read, is_starred, is_deleted,
            body_fetched, received_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(uuid) DO UPDATE SET
               account_email  = excluded.account_email,
               folder_name    = excluded.folder_name,
               message_id     = excluded.message_id,
               in_reply_to    = excluded.in_reply_to,
               imap_uid       = excluded.imap_uid,
               from_addr      = excluded.from_addr,
               to_recipients  = excluded.to_recipients,
               cc_recipients  = excluded.cc_recipients,
               subject        = excluded.subject,
               body           = excluded.body,
               html_body      = excluded.html_body,
               priority       = excluded.priority,
                -- Preserve local is_read/is_starred/is_deleted — never overwrite
                -- user's read/favourite/trash state with IMAP data.
                is_read        = COALESCE((SELECT is_read FROM messages WHERE uuid = excluded.uuid), excluded.is_read),
                is_starred     = COALESCE((SELECT is_starred FROM messages WHERE uuid = excluded.uuid), excluded.is_starred),
                is_deleted     = COALESCE((SELECT is_deleted FROM messages WHERE uuid = excluded.uuid), excluded.is_deleted),
               body_fetched   = excluded.body_fetched,
               received_at    = excluded.received_at,
               created_at     = excluded.created_at,
               updated_at     = excluded.updated_at""",
        (msg_uuid, account_email or data.get("account_email", ""),
         folder_name or data.get("folder_name"),
         data.get("message_id", ""), data.get("in_reply_to", ""),
         data.get("imap_uid"), data.get("from_addr", ""), data.get("to_recipients", "[]"),
         data.get("cc_recipients", "[]"), data.get("subject", ""), data.get("body", ""),
         data.get("html_body", ""), data.get("priority", 5),
         int(data.get("is_read", 0)), int(data.get("is_starred", 0)),
         int(data.get("is_deleted", 0)),
         int(data.get("body_fetched", 1)), data.get("received_at", ""),
         data.get("created_at", ""), data.get("updated_at", "")),
    )
