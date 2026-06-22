"""Journal CRUD service."""

from __future__ import annotations

from typing import Any

from lighterbird.core.crud import CRUDService


class JournalService(CRUDService):
    """CRUD service for taglibro (journal entries)."""

    def __init__(self, db):
        super().__init__(db, "taglibro")

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
