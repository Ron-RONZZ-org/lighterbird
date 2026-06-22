"""Todo CRUD service."""

from __future__ import annotations

from typing import Any

from lighterbird.core.crud import CRUDService


class TodoService(CRUDService):
    """CRUD service for taskoj (todos)."""

    def __init__(self, db):
        super().__init__(db, "taskoj")

    def search(self, query: str, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if not query and not status:
            return self.list(limit=limit)
        conditions = []
        params: list[Any] = []
        if query:
            conditions.append("(LOWER(titolo) LIKE LOWER(?) OR LOWER(priskribo) LIKE LOWER(?))")
            params.extend([f"%{query}%", f"%{query}%"])
        if status:
            conditions.append("stato = ?")
            params.append(status)
        where = " AND ".join(conditions)
        return self.db.execute(
            f"SELECT * FROM taskoj WHERE {where} ORDER BY prioritato ASC, kreita_je DESC LIMIT ?",
            (*params, limit),
        )

    def mark_done(self, uuid_: str) -> bool:
        """Mark a todo as done."""
        result = self.update(uuid_, {"stato": "done"})
        return result is not None
