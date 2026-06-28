"""Journal CRUD service with label management."""

from __future__ import annotations

from typing import Any

from lighterbird.core.crud import CRUDService


class JournalService(CRUDService):
    """CRUD service for taglibro (journal entries) with labels."""

    def __init__(self, db):
        super().__init__(db, "taglibro")

    # ── Search ──────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        if not query:
            return self.list(limit=limit)
        return self.db.execute(
            "SELECT * FROM taglibro WHERE "
            "LOWER(titolo) LIKE LOWER(?) OR LOWER(teksto) LIKE LOWER(?) "
            "ORDER BY dato DESC, kreita_je DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        )

    def list_by_date(self, date_str: str) -> list[dict[str, Any]]:
        return self.db.execute(
            "SELECT * FROM taglibro WHERE dato = ? ORDER BY kreita_je ASC",
            (date_str,),
        )

    # ── Labels ──────────────────────────────────────────────────────────

    def add_label(self, entry_uuid: str, label_teksto: str) -> None:
        """Attach a label to a journal entry."""
        self.db.execute(
            "INSERT OR IGNORE INTO taglibro_etikedo (taglibro_uuid, etikedo_teksto) "
            "VALUES (?, ?)",
            (entry_uuid, label_teksto),
        )

    def remove_label(self, entry_uuid: str, label_teksto: str) -> None:
        """Detach a label from a journal entry."""
        self.db.execute(
            "DELETE FROM taglibro_etikedo "
            "WHERE taglibro_uuid = ? AND etikedo_teksto = ?",
            (entry_uuid, label_teksto),
        )

    def get_labels(self, entry_uuid: str) -> list[dict[str, Any]]:
        """Get all labels attached to a journal entry."""
        return self.db.execute(
            "SELECT e.* FROM etikedoj e "
            "JOIN taglibro_etikedo te ON e.teksto = te.etikedo_teksto "
            "WHERE te.taglibro_uuid = ? ORDER BY e.teksto",
            (entry_uuid,),
        )

    def list_all_labels(self) -> list[dict[str, Any]]:
        """List all available labels."""
        return self.db.execute("SELECT * FROM etikedoj ORDER BY teksto")

    def create_label(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new label."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        teksto = data.get("teksto", "").strip()
        if not teksto:
            raise ValueError("Label text (teksto) is required.")
        koloro = data.get("koloro", "")
        try:
            return self.db.execute_one(
                "INSERT INTO etikedoj (teksto, koloro, kreita_je, modifita_je) "
                "VALUES (?, ?, ?, ?) RETURNING *",
                (teksto, koloro, now, now),
            )
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError(f"Label '{teksto}' already exists.") from e
            raise

    def delete_label(self, label_teksto: str) -> None:
        """Delete a label and all its associations."""
        self.db.execute("DELETE FROM etikedoj WHERE teksto = ?", (label_teksto,))
