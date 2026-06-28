"""Journal CRUD service with label management."""

from __future__ import annotations

from typing import Any

from lighterbird.core.crud import CRUDService


class JournalService(CRUDService):
    """CRUD service for journal (journal entries) with labels."""

    def __init__(self, db):
        super().__init__(db, "journal")

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
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
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
