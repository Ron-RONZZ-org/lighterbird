"""Contact CRUD service."""

from __future__ import annotations

from typing import Any

from lighterbird.core.crud import CRUDService


class ContactService(CRUDService):
    """CRUD service for kontaktoj (contacts)."""

    def __init__(self, db):
        super().__init__(db, "kontaktoj")

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search contacts by name or email."""
        if not query:
            return self.list(limit=limit)
        return self.db.execute(
            "SELECT * FROM kontaktoj WHERE "
            "LOWER(nomo) LIKE LOWER(?) OR LOWER(retposto) LIKE LOWER(?) "
            "ORDER BY nomo ASC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        )

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        return self.db.execute_one(
            "SELECT * FROM kontaktoj WHERE LOWER(retposto) = LOWER(?)",
            (email.strip(),),
        )
