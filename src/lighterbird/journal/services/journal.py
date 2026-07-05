"""Journal CRUD service with label management."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any

from lighterbird.core.crud import CRUDService
from lighterbird.core.yaml_frontmatter import unwrap, wrap


class JournalService(CRUDService):
    """CRUD service for journal (journal entries) with labels."""

    def __init__(self, db):
        super().__init__(db, "journal")

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a journal entry with a default date if not provided."""
        from datetime import UTC, datetime

        data = dict(data)
        data.setdefault("date", datetime.now(UTC).date().isoformat())
        return super().create(data)

    # ── Markdown export / import ────────────────────────────────────────

    def export_md(self, uuid: str | None = None, uuids: list[str] | None = None) -> str:
        """Export one or more journal entries as a .md string with YAML frontmatter.

        Args:
            uuid: Single entry UUID.
            uuids: Multiple entry UUIDs.

        Returns:
            Full markdown string(s) concatenated with ``---`` separators.
        """
        ids: list[str] = []
        if uuids:
            ids.extend(uuids)
        if uuid:
            ids.append(uuid)

        parts: list[str] = []
        for eid in ids:
            entry = self.get(eid)
            if not entry:
                continue
            meta = {
                "uuid": entry["uuid"],
                "domain": "journal",
                "created_at": entry.get("created_at"),
                "updated_at": entry.get("updated_at"),
                "date": entry.get("date"),
                "title": entry.get("title", ""),
            }
            body = entry.get("text", "")
            parts.append(wrap(body, meta))
        return "\n---\n".join(parts)

    def import_md(self, path: str) -> list[str]:
        """Import a .md file with YAML frontmatter as journal entry(s).

        Parses the frontmatter block (``---...---``) from the file and
        creates a journal entry from the metadata and body text.

        Args:
            path: Path to the .md file.

        Returns:
            List of created UUIDs.
        """
        text = Path(path).read_text(encoding="utf-8")
        meta, body = unwrap(text)
        if not meta:
            return []

        entry_data = {
            "title": meta.get("title", ""),
            "text": body,
            "date": meta.get("date", ""),
        }
        if meta.get("created_at"):
            entry_data["created_at"] = meta["created_at"]
        if meta.get("updated_at"):
            entry_data["updated_at"] = meta["updated_at"]
        # Don't pass uuid from frontmatter — let create() generate a new one
        # so re-importing an exported file doesn't hit UNIQUE constraint.
        entry = self.create(entry_data)
        return [entry["uuid"]]

    # ── Search ──────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        if not query:
            return self.list(limit=limit)
        return self.db.execute(
            "SELECT * FROM journal WHERE "
            "LOWER(title) LIKE LOWER(?) OR LOWER(text) LIKE LOWER(?) "
            "ORDER BY date DESC, created_at DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        )

    def list_by_date(self, date_str: str) -> list[dict[str, Any]]:
        return self.db.execute(
            "SELECT * FROM journal WHERE date = ? ORDER BY created_at ASC",
            (date_str,),
        )

    # ── Labels ──────────────────────────────────────────────────────────

    def add_label(self, entry_uuid: str, label_name: str) -> None:
        """Attach a label to a journal entry."""
        self.db.execute(
            "INSERT OR IGNORE INTO journal_labels (entry_uuid, label_name) "
            "VALUES (?, ?)",
            (entry_uuid, label_name),
        )

    def remove_label(self, entry_uuid: str, label_name: str) -> None:
        """Detach a label from a journal entry."""
        self.db.execute(
            "DELETE FROM journal_labels "
            "WHERE entry_uuid = ? AND label_name = ?",
            (entry_uuid, label_name),
        )

    def get_labels(self, entry_uuid: str) -> list[dict[str, Any]]:
        """Get all labels attached to a journal entry."""
        return self.db.execute(
            "SELECT l.* FROM labels l "
            "JOIN journal_labels jl ON l.name = jl.label_name "
            "WHERE jl.entry_uuid = ? ORDER BY l.name",
            (entry_uuid,),
        )

    def list_all_labels(self) -> list[dict[str, Any]]:
        """List all available labels."""
        return self.db.execute("SELECT * FROM labels ORDER BY name")

    def create_label(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new label."""
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        name = data.get("name", "").strip()
        if not name:
            raise ValueError("Label name is required.")
        color = data.get("color", "")
        try:
            return self.db.execute_one(
                "INSERT INTO labels (name, color, created_at, updated_at) "
                "VALUES (?, ?, ?, ?) RETURNING *",
                (name, color, now, now),
            )
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError(f"Label '{name}' already exists.") from e
            raise

    def delete_label(self, label_name: str) -> None:
        """Delete a label and all its associations."""
        self.db.execute("DELETE FROM labels WHERE name = ?", (label_name,))
