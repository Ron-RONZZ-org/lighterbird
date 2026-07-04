"""Message query service.

Flat service class, forked from A-lien's RetpostoMessagingMixin.
"""

from __future__ import annotations

import email.message
from typing import Any


class MessageService:
    """Read-only message queries."""

    def __init__(self, db):
        self.db = db

    def get_message(self, uuid_: str) -> dict[str, Any] | None:
        """Get a non-deleted message by UUID."""
        return self.db.execute_one(
            "SELECT * FROM messages WHERE uuid = ? AND is_deleted = 0", (uuid_,)
        )

    def find_by_uuid_prefix(self, prefix: str) -> list[dict[str, Any]]:
        """Find non-deleted messages by UUID prefix."""
        if not prefix:
            return []
        return list(
            self.db.execute(
                "SELECT * FROM messages WHERE uuid LIKE ? AND is_deleted = 0",
                (f"{prefix}%",),
            )
        )

    def list_messages(
        self,
        account_email: str | None = None,
        folder: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = "newest",
    ) -> list[dict[str, Any]]:
        """List non-deleted messages, optionally filtered."""
        conditions = ["m.is_deleted = 0"]
        params: list[Any] = []
        if account_email:
            conditions.append("m.account_email = ?")
            params.append(account_email)
        if folder:
            conditions.append("m.folder_name = ?")
            params.append(folder)
        where = " AND ".join(conditions)
        order = "m.received_at DESC" if sort != "oldest" else "m.received_at ASC"
        sql = (
            "SELECT m.*, COALESCE(m.folder_name, '') AS folder_name"
            " FROM messages m"
            f" WHERE {where}"
            f" ORDER BY {order} LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        return list(self.db.execute(sql, tuple(params)))

    def search_messages(
        self, filters: dict[str, Any], limit: int = 50
    ) -> list[dict[str, Any]]:
        """Search messages with filters."""
        conditions = ["m.is_deleted = 0"]
        params: list[Any] = []
        if filters.get("query"):
            conditions.append("(m.subject LIKE ? OR m.body LIKE ?)")
            q = f"%{filters['query']}%"
            params.extend([q, q])
        if filters.get("from"):
            conditions.append("m.de LIKE ?")
            params.append(f"%{filters['from']}%")
        if filters.get("to"):
            conditions.append("m.al LIKE ?")
            params.append(f"%{filters['to']}%")
        if filters.get("subject"):
            conditions.append("m.subject LIKE ?")
            params.append(f"%{filters['subject']}%")
        if filters.get("body"):
            conditions.append("m.body LIKE ?")
            params.append(f"%{filters['body']}%")
        if filters.get("after"):
            conditions.append("m.received_at >= ?")
            params.append(filters["after"])
        if filters.get("before"):
            conditions.append("m.received_at <= ?")
            params.append(filters["before"])
        if filters.get("read") is not None:
            conditions.append("m.is_read = ?")
            params.append(1 if filters["read"] else 0)
        if filters.get("account"):
            conditions.append("m.account_email = ?")
            params.append(filters["account"])
        # Folder filtering: list of folders to INCLUDE (by name)
        folder_names = filters.get("folder")
        if folder_names:
            if isinstance(folder_names, str):
                folder_names = [folder_names]
            placeholders = ",".join("?" for _ in folder_names)
            conditions.append(f"m.folder_name IN ({placeholders})")
            params.extend(folder_names)
        # Exclude specific folders (e.g. Trash)
        exclude_folders = filters.get("exclude_folder")
        if exclude_folders:
            if isinstance(exclude_folders, str):
                exclude_folders = [exclude_folders]
            placeholders = ",".join("?" for _ in exclude_folders)
            conditions.append(
                f"(m.folder_name IS NULL OR m.folder_name NOT IN ({placeholders}))"
            )
            params.extend(exclude_folders)
        where = " AND ".join(conditions)

        # Sorting
        sort = filters.get("sort", "newest")
        if sort == "oldest":
            order = "m.received_at ASC"
        else:
            order = "m.received_at DESC"

        # Group by sender (overrides received_at ordering for display grouping)
        group = filters.get("group", "")
        if group == "sender":
            select_cols = "m.*, COALESCE(m.from_addr, '') AS sort_sender"
            order = f"LOWER(COALESCE(m.from_addr, '')), {order}"
        else:
            select_cols = "m.*"

        sql = (
            f"SELECT {select_cols}"
            " FROM messages m"
            f" WHERE {where}"
            f" ORDER BY {order} LIMIT ?"
        )
        params.append(limit)
        try:
            rows = self.db.execute(sql, tuple(params))
        except Exception:
            fallback_sql = (
                f"SELECT {select_cols} FROM messages m"
                " WHERE m.is_deleted = 0"
                f" ORDER BY {order} LIMIT ?"
            )
            rows = self.db.execute(fallback_sql, (limit,))
        return list(rows)

    def export_eml(self, uuid_: str) -> str | None:
        """Export a message as an RFC 822 .eml string.

        Returns the .eml content or None if the message is not found.
        """
        msg = self.get_message(uuid_)
        if not msg:
            return None

        eml = email.message.EmailMessage()
        eml["From"] = msg.get("from_addr", "")
        eml["To"] = msg.get("to_recipients", "")
        eml["Subject"] = msg.get("subject", "")
        eml["Date"] = msg.get("received_at", "")
        if msg.get("message_id"):
            eml["Message-ID"] = msg["message_id"]
        body = msg.get("body", "")
        eml.set_content(body or "")

        return eml.as_string()

    def find_conversation(
        self, message_id: str, references: str = "", in_reply_to: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find messages in the same conversation thread."""
        ids = set()
        if message_id:
            ids.add(message_id)
        if in_reply_to:
            for rid in in_reply_to.split():
                rid = rid.strip()
                if rid:
                    ids.add(rid)
        if references:
            for rid in references.split():
                rid = rid.strip()
                if rid:
                    ids.add(rid)

        if not ids:
            return []

        placeholders = ",".join("?" for _ in ids)
        sql = (
            "SELECT m.* FROM messages m"
            " WHERE m.is_deleted = 0"
            " AND (m.message_id IN ({p}) OR m.in_reply_to IN ({p})"
            "      OR m.references IN ({p})"
            "      OR EXISTS ("
            "        SELECT 1 FROM messages m2"
            "        WHERE m2.message_id IN ({p})"
            "        AND (m.references LIKE '%' || m2.message_id || '%'"
            "             OR m.in_reply_to LIKE '%' || m2.message_id || '%')"
            "      ))"
            " ORDER BY m.received_at ASC"
            " LIMIT ?"
        ).format(p=placeholders)
        params = list(ids) * 4 + [limit]
        return list(self.db.execute(sql, tuple(params)))
