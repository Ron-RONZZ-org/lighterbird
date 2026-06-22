"""Calendar and event services.

Flat service classes, forked from A-organizi's service/kalendaro.py.
Stripped of CalDAV sync hooks for MVP (local-only events).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from lighterbird.core.crud import CRUDService


class CalendarCRUD(CRUDService):
    """CRUD service for kalendaroj (calendars)."""

    def __init__(self, db):
        super().__init__(db, "kalendaroj")

    def find_by_uuid_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        return super().find_by_uuid_prefix(prefix.lstrip("#"), limit=limit)

    def resolve_uuid(self, ref: str) -> str | None:
        """Resolve a user reference to a calendar UUID."""
        token = ref.lstrip("#")
        row = self.db.execute_one("SELECT uuid FROM kalendaroj WHERE uuid = ?", (token,))
        if row:
            return str(row["uuid"])
        rows = self.db.execute(
            "SELECT uuid FROM kalendaroj WHERE uuid LIKE ? ORDER BY uuid",
            (f"{token}%",),
        )
        if len(rows) == 1:
            return str(rows[0]["uuid"])
        return None

    def calendar_exists(self, url: str, username: str) -> bool:
        """Check if a calendar with the given URL and username exists."""
        row = self.db.execute_one(
            "SELECT 1 FROM kalendaroj WHERE LOWER(url)=LOWER(?) AND LOWER(username)=LOWER(?)",
            (url.strip(), username.strip()),
        )
        return row is not None

    def delete(self, uuid_: str, soft: bool = True) -> bool:
        """Delete a calendar and all its events."""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM eventoj WHERE kalendaro_uuid = ?", (uuid_,))
            conn.execute("DELETE FROM kalendaroj WHERE uuid = ?", (uuid_,))
        return True


class EventService(CRUDService):
    """CRUD service for eventoj (events) with date-range queries."""

    def __init__(self, db):
        super().__init__(db, "eventoj")

    def find_by_uuid_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        return super().find_by_uuid_prefix(prefix.lstrip("#"), limit=limit)

    def list_by_date_range(
        self,
        start: str,
        end: str,
        calendar_uuids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List events in a date range, optionally filtered by calendar."""
        params: list[Any] = [start, end]
        query = "SELECT * FROM eventoj WHERE date(komenco) >= ? AND date(komenco) <= ?"
        if calendar_uuids:
            placeholders = ",".join("?" for _ in calendar_uuids)
            query += f" AND kalendaro_uuid IN ({placeholders})"
            params.extend(calendar_uuids)
        query += " ORDER BY komenco ASC"
        return self.db.execute(query, tuple(params))
