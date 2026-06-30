"""Letter CRUD service with conversation grouping, search, and body management."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lighterbird.core.crud import CRUDService


class LetterService(CRUDService):
    """CRUD service for paper letters."""

    def __init__(self, db):
        super().__init__(db, "letters")

    # ── List with filters ──────────────────────────────────────────────

    def list(
        self,
        order_by: str = "created_at",
        desc: bool = True,
        limit: int | None = 50,
        offset: int | None = None,
        direction: str | None = None,
        sender: str | None = None,
        recipient: str | None = None,
        object_query: str | None = None,
        date_after: str | None = None,
        date_before: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []

        if direction and direction != "all":
            conditions.append("direction = ?")
            params.append(direction)

        if sender:
            conditions.append("(LOWER(sender_manual) LIKE LOWER(?) OR sender_profile = ?)")
            params.extend([f"%{sender}%", sender])

        if recipient:
            conditions.append("(LOWER(recipient_manual) LIKE LOWER(?) OR recipient_contact = ?)")
            params.extend([f"%{recipient}%", recipient])

        if object_query:
            conditions.append("LOWER(object) LIKE LOWER(?)")
            params.append(f"%{object_query}%")

        if date_after:
            conditions.append("created_at >= ?")
            params.append(date_after)

        if date_before:
            conditions.append("created_at <= ?")
            params.append(date_before)

        where = ""
        if conditions:
            where = " WHERE " + " AND ".join(conditions)

        sort_order = "DESC" if desc else "ASC"
        sql = f"SELECT * FROM {self.table}{where} ORDER BY {order_by} {sort_order}"

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        if offset is not None:
            sql += " OFFSET ?"
            params.append(offset)

        return self.db.execute(sql, tuple(params))

    # ── Get with conversation thread ───────────────────────────────────

    def get_with_thread(self, uuid_: str) -> dict[str, Any] | None:
        """Get a letter plus its full conversation thread."""
        letter = self.get(uuid_)
        if not letter:
            return None
        thread = self._get_thread(uuid_)
        letter["thread"] = thread
        return letter

    def _get_thread(self, uuid_: str) -> list[dict[str, Any]]:
        """Get all letters in a conversation thread (linked via respond_to_uuid)."""
        return self.db.execute(
            "WITH RECURSIVE thread(uuid, respond_to_uuid) AS ("
            "  SELECT uuid, respond_to_uuid FROM letters WHERE uuid = ?"
            "  UNION ALL"
            "  SELECT l.uuid, l.respond_to_uuid FROM letters l"
            "  JOIN thread ON l.uuid = thread.respond_to_uuid"
            "  OR l.respond_to_uuid = thread.uuid"
            "  WHERE l.uuid != thread.uuid"
            ") SELECT DISTINCT letters.* FROM letters"
            " JOIN thread ON letters.uuid = thread.uuid"
            " ORDER BY letters.created_at ASC",
            (uuid_,),
        )

    # ── Search ─────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        if not query:
            return self.list(limit=limit)
        like_q = f"%{query}%"
        return self.db.execute(
            "SELECT * FROM letters WHERE"
            " LOWER(object) LIKE LOWER(?)"
            " OR LOWER(sender_manual) LIKE LOWER(?)"
            " OR LOWER(recipient_manual) LIKE LOWER(?)"
            " ORDER BY created_at DESC LIMIT ?",
            (like_q, like_q, like_q, limit),
        )

    # ── Conversation-grouped listing ───────────────────────────────────

    def list_grouped(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return letters grouped by conversation (root + replies)."""
        roots = self.db.execute(
            "SELECT * FROM letters WHERE respond_to_uuid IS NULL"
            " ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        result = []
        for root in roots:
            replies = self.db.execute(
                "SELECT * FROM letters WHERE respond_to_uuid = ?"
                " ORDER BY created_at ASC",
                (root["uuid"],),
            )
            root["replies"] = replies
            result.append(root)
        return result

    # ── Body content management ────────────────────────────────────────

    def _body_storage_path(self, uuid_: str) -> Path:
        from lighterbird.core.paths import data_dir
        letter_dir = data_dir() / "letters" / "bodies"
        letter_dir.mkdir(parents=True, exist_ok=True)
        return letter_dir / f"{uuid_}.html"

    def store_body(self, uuid_: str, html_content: str) -> str:
        """Store HTML body content to disk and return the file path."""
        path = self._body_storage_path(uuid_)
        path.write_text(html_content, encoding="utf-8")
        self.update(uuid_, {"body_path": str(path), "body_format": "html"})
        return str(path)

    def get_body(self, uuid_: str) -> str:
        """Read the HTML body content from disk."""
        letter = self.get(uuid_)
        if not letter or not letter.get("body_path"):
            return ""
        path = Path(letter["body_path"])
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def convert_to_html(self, content: str, fmt: str) -> str:
        """Convert markdown or plain text to HTML."""
        if fmt == "html":
            return content
        if fmt == "markdown":
            try:
                import markdown as md_lib
                return md_lib.markdown(content)
            except ImportError:
                pass
            lines = []
            in_para = False
            for line in content.split("\n"):
                stripped = line.strip()
                if not stripped:
                    if in_para:
                        lines.append("</p>")
                        in_para = False
                    continue
                if stripped.startswith("# "):
                    if in_para:
                        lines.append("</p>")
                        in_para = False
                    lines.append(f"<h1>{stripped[2:]}</h1>")
                elif stripped.startswith("## "):
                    if in_para:
                        lines.append("</p>")
                        in_para = False
                    lines.append(f"<h2>{stripped[3:]}</h2>")
                elif stripped.startswith("### "):
                    if in_para:
                        lines.append("</p>")
                        in_para = False
                    lines.append(f"<h3>{stripped[4:]}</h3>")
                else:
                    if not in_para:
                        lines.append("<p>")
                        in_para = True
                    lines.append(stripped)
            if in_para:
                lines.append("</p>")
            return "\n".join(lines)
        return f"<pre>{content}</pre>"
