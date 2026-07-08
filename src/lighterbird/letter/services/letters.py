"""Letter CRUD service with conversation grouping, search, and body management."""

from __future__ import annotations

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
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []

        if direction and direction != "all":
            conditions.append("l.direction = ?")
            params.append(direction)

        if sender:
            conditions.append("(LOWER(l.sender_manual) LIKE LOWER(?) OR l.sender_profile = ?)")
            params.extend([f"%{sender}%", sender])

        if recipient:
            conditions.append("(LOWER(l.recipient_manual) LIKE LOWER(?) OR l.recipient_contact = ?)")
            params.extend([f"%{recipient}%", recipient])

        if object_query:
            conditions.append("LOWER(l.object) LIKE LOWER(?)")
            params.append(f"%{object_query}%")

        if date_after:
            conditions.append("l.created_at >= ?")
            params.append(date_after)

        if date_before:
            conditions.append("l.created_at <= ?")
            params.append(date_before)

        # Tag filter: letters must have ALL specified tags (AND semantics)
        if tags:
            for tag in tags:
                conditions.append(
                    "EXISTS (SELECT 1 FROM letter_tags lt WHERE lt.letter_uuid = l.uuid AND lt.tag = ?)"
                )
                params.append(tag)

        from_clause = f"{self.table} l"
        where = ""
        if conditions:
            where = " WHERE " + " AND ".join(conditions)

        sort_order = "DESC" if desc else "ASC"
        sql = f"SELECT l.* FROM {from_clause}{where} ORDER BY l.{order_by} {sort_order}"

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        if offset is not None:
            sql += " OFFSET ?"
            params.append(offset)

        results = self.db.execute(sql, tuple(params))
        return self._attach_tags(results)

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
        """Get all letters in a conversation thread (linked via respond_to_uuid).

        Uses a path-based cycle guard to prevent infinite loops in the
        bidirectional recursive traversal (e.g. A→B→A→…).
        """
        return self.db.execute(
            "WITH RECURSIVE thread(uuid, respond_to_uuid, path) AS ("
            "  SELECT uuid, respond_to_uuid, ',' || uuid || ',' FROM letters WHERE uuid = ?"
            "  UNION ALL"
            "  SELECT l.uuid, l.respond_to_uuid, thread.path || l.uuid || ','"
            "  FROM letters l"
            "  JOIN thread ON l.uuid = thread.respond_to_uuid"
            "  OR l.respond_to_uuid = thread.uuid"
            "  WHERE instr(thread.path, ',' || l.uuid || ',') = 0"
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
        results = self.db.execute(
            "SELECT * FROM letters WHERE"
            " LOWER(object) LIKE LOWER(?)"
            " OR LOWER(sender_manual) LIKE LOWER(?)"
            " OR LOWER(recipient_manual) LIKE LOWER(?)"
            " ORDER BY created_at DESC LIMIT ?",
            (like_q, like_q, like_q, limit),
        )
        return self._attach_tags(results)

    # ── Conversation-grouped listing ───────────────────────────────────

    def list_grouped(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return letters grouped by conversation (root + replies).

        Uses a single batch query for replies instead of N+1 queries.
        """
        roots = list(self.db.execute(
            "SELECT * FROM letters WHERE respond_to_uuid IS NULL"
            " ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ))
        if not roots:
            return []

        # Batch-fetch all replies in a single query
        root_uuids = [r["uuid"] for r in roots]
        placeholders = ",".join("?" for _ in root_uuids)
        all_replies = list(self.db.execute(
            f"SELECT * FROM letters WHERE respond_to_uuid IN ({placeholders})"
            " ORDER BY created_at ASC",
            tuple(root_uuids),
        ))

        # Group replies by respond_to_uuid
        reply_map: dict[str, list[dict[str, Any]]] = {}
        for reply in all_replies:
            reply_map.setdefault(reply["respond_to_uuid"], []).append(reply)

        result = []
        for root in roots:
            root["replies"] = reply_map.get(root["uuid"], [])
            result.append(root)
        return self._attach_tags(result)

    # ── Tag management ────────────────────────────────────────────────

    @staticmethod
    def normalize_tags(raw_tags: list[str]) -> list[str]:
        """Normalize tag strings: lowercase, strip, filter empty, expand commas.

        Handles both ``--tag a --tag b`` (list of single tags) and
        ``--tag a,b`` (comma-separated in one flag).
        """
        seen: set[str] = set()
        result: list[str] = []
        for raw in raw_tags:
            for part in raw.split(","):
                t = part.strip().lower()
                if t and t not in seen:
                    seen.add(t)
                    result.append(t)
        return result

    def set_tags(self, uuid_: str, tags: list[str]) -> None:
        """Replace all tags for a letter."""
        self.db.execute("DELETE FROM letter_tags WHERE letter_uuid = ?", (uuid_,))
        for tag in tags:
            self.db.execute(
                "INSERT OR IGNORE INTO letter_tags (letter_uuid, tag) VALUES (?, ?)",
                (uuid_, tag),
            )

    def add_tags(self, uuid_: str, tags: list[str]) -> None:
        """Add tags to a letter (merging with existing)."""
        for tag in tags:
            self.db.execute(
                "INSERT OR IGNORE INTO letter_tags (letter_uuid, tag) VALUES (?, ?)",
                (uuid_, tag),
            )

    def remove_tags(self, uuid_: str, tags: list[str]) -> None:
        """Remove specific tags from a letter."""
        for tag in tags:
            self.db.execute(
                "DELETE FROM letter_tags WHERE letter_uuid = ? AND tag = ?",
                (uuid_, tag),
            )

    def get_tags(self, uuid_: str) -> list[str]:
        """Get all tags for a letter."""
        rows = self.db.execute(
            "SELECT tag FROM letter_tags WHERE letter_uuid = ? ORDER BY tag",
            (uuid_,),
        )
        return [r["tag"] for r in rows]

    def _attach_tags(self, letters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach tags to a list of letter dicts (batch query)."""
        if not letters:
            return letters
        uuids = [l["uuid"] for l in letters]
        placeholders = ",".join("?" for _ in uuids)
        rows = self.db.execute(
            f"SELECT letter_uuid, tag FROM letter_tags WHERE letter_uuid IN ({placeholders}) ORDER BY tag",
            tuple(uuids),
        )
        tag_map: dict[str, list[str]] = {}
        for r in rows:
            tag_map.setdefault(r["letter_uuid"], []).append(r["tag"])
        for l in letters:
            l["tags"] = tag_map.get(l["uuid"], [])
        return letters

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

    @staticmethod
    def _inline_markdown(text: str) -> str:
        """Convert inline markdown syntax (**bold**, *italic*, `code`) to HTML."""
        import re
        # Bold: **text** or __text__
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
        # Italic: *text* or _text_
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
        text = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<em>\1</em>', text)
        # Inline code: `text`
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        return text

    # ── MD export/import ─────────────────────────────────────────────

    def export_md(self, uuid: str | None = None, uuids: list[str] | None = None) -> str:
        """Export one or more letters as YAML-frontmatter markdown.

        Args:
            uuid: Single letter UUID.
            uuids: Batch list of UUIDs (takes precedence over *uuid*).

        Returns:
            Concatenated markdown string with frontmatter per letter.
        """
        from lighterbird.core.yaml_frontmatter import wrap

        targets: list[str] = []
        if uuids:
            targets = uuids
        elif uuid:
            targets = [uuid]

        parts: list[str] = []
        for uid in targets:
            letter = self.get(uid)
            if not letter:
                continue
            body = self.get_body(uid)
            plain_body = self._html_to_text(body)
            tags = self.get_tags(uid)
            meta = {
                "uuid": letter.get("uuid"),
                "domain": "letter",
                "created_at": letter.get("created_at"),
                "updated_at": letter.get("updated_at"),
                "direction": letter.get("direction"),
                "object": letter.get("object"),
                "sender_manual": letter.get("sender_manual"),
                "recipient_manual": letter.get("recipient_manual"),
                "tags": tags if tags else None,
            }
            parts.append(wrap(plain_body, meta))

        return "\n".join(parts)

    def import_md(self, path: str) -> list[str]:
        """Import a YAML-frontmatter markdown file as one or more letters.

        Args:
            path: Absolute path to the .md file.

        Returns:
            List of created letter UUIDs.
        """
        from pathlib import Path

        from lighterbird.core.yaml_frontmatter import unwrap

        filepath = Path(path)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = filepath.read_text(encoding="utf-8")
        meta, body = unwrap(content)

        data: dict[str, Any] = {
            "direction": meta.get("direction", "received"),
            "object": meta.get("object", ""),
            "sender_manual": meta.get("sender_manual", ""),
            "recipient_manual": meta.get("recipient_manual", ""),
        }

        if meta.get("uuid"):
            data["uuid"] = meta["uuid"]
        if meta.get("created_at"):
            data["created_at"] = meta["created_at"]
        if meta.get("updated_at"):
            data["updated_at"] = meta["updated_at"]

        letter = self.create(data)

        if body:
            html_content = self.convert_to_html(body, "markdown")
            self.store_body(letter["uuid"], html_content)

        tags = meta.get("tags")
        if tags:
            if isinstance(tags, list):
                self.set_tags(letter["uuid"], tags)
            elif isinstance(tags, str):
                self.set_tags(letter["uuid"], [tags])

        return [letter["uuid"]]

    @staticmethod
    def _html_to_text(html_content: str) -> str:
        """Strip HTML tags and entities to produce readable plain text."""
        import re
        if not html_content:
            return ""
        clean = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL)
        clean = re.sub(r'<script[^>]*>.*?</script>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<br\s*/?>', '\n', clean)
        clean = re.sub(r'</p>', '\n\n', clean)
        clean = re.sub(r'</div>', '\n', clean)
        clean = re.sub(r'<[^>]+>', '', clean)
        clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        clean = clean.replace('&quot;', '"').replace('&#39;', "'")
        clean = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), clean)
        clean = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), clean)
        return clean.strip()

    def convert_to_html(self, content: str, fmt: str) -> str:
        """Convert markdown or plain text to HTML (delegates to shared utility)."""
        from lighterbird.server.render_utils import convert_to_html as _convert

        return _convert(content, fmt)
