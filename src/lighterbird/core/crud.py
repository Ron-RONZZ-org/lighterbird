"""CRUD service base class for lighterbird.

Simplified fork of A-core's ``A.core.service.CRUDService``.
Stripped of FTS5, undo stack, fuzzy search, and soft-delete for the MVP.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from lighterbird.core.db import LighterbirdDB


class CRUDService:
    """CRUD operations with auto-timestamps (kreita_je, modifita_je).

    This is a simplified base class. Domain-specific services (accounts,
    messages, calendars, events) subclass this and add their own methods.
    """

    def __init__(self, db: LighterbirdDB, table: str):
        self.db = db
        self.table = table

    # ── Hooks (override in subclass) ────────────────────────────────────

    def _post_create(self, data: dict[str, Any], result: dict[str, Any]) -> None:
        """Called after successful create. Override in subclass."""

    def _post_update(
        self, uuid: str, old_data: dict[str, Any] | None, new_data: dict[str, Any]
    ) -> None:
        """Called after successful update. Override in subclass."""

    def _post_delete(self, uuid: str, data: dict[str, Any] | None) -> None:
        """Called after successful delete. Override in subclass."""

    # ── List / Get ──────────────────────────────────────────────────────

    def list(
        self,
        order_by: str = "kreita_je",
        desc: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """List all entries, optionally ordered and limited."""
        direction = "DESC" if desc else "ASC"
        sql = f"SELECT * FROM {self.table} ORDER BY {order_by} {direction}"
        params: list[Any] = []
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        if offset is not None:
            sql += " OFFSET ?"
            params.append(offset)
        return self.db.execute(sql, tuple(params))

    def get(self, uuid_: str) -> dict[str, Any] | None:
        """Get a single entry by UUID (supports prefix matching)."""
        return self.db.execute_one(
            f"SELECT * FROM {self.table} WHERE uuid LIKE ?",
            (f"{uuid_}%",),
        )

    def find_by_uuid_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find entries whose UUID starts with the given prefix."""
        if not prefix:
            return []
        return self.db.execute(
            f"SELECT * FROM {self.table} WHERE uuid LIKE ? "
            f"ORDER BY kreita_je DESC LIMIT ?",
            (f"{prefix}%", limit),
        )

    def search(
        self, field: str, query: str, case_sensitive: bool = False
    ) -> list[dict[str, Any]]:
        """Search entries by field containing a substring."""
        if case_sensitive:
            sql = f"SELECT * FROM {self.table} WHERE {field} LIKE ?"
        else:
            sql = f"SELECT * FROM {self.table} WHERE LOWER({field}) LIKE LOWER(?)"
        return self.db.execute(sql, (f"%{query}%",))

    # ── Create / Update / Delete ────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new entry with auto-generated UUID and timestamps."""
        now = datetime.now(timezone.utc).isoformat()
        data.setdefault("uuid", str(uuid.uuid4()))
        data.setdefault("kreita_je", now)
        data["modifita_je"] = now

        columns = list(data.keys())
        values = list(data.values())
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})"

        with self.db.transaction() as conn:
            conn.execute(sql, values)

        result = data.copy()
        self._post_create(data, result)
        return result

    def update(self, uuid_: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an entry, preserving creation timestamp."""
        old_data = self.get(uuid_)
        data["modifita_je"] = datetime.now(timezone.utc).isoformat()

        set_clauses = [f"{k} = ?" for k in data.keys()]
        values = list(data.values()) + [uuid_]
        sql = f"UPDATE {self.table} SET {', '.join(set_clauses)} WHERE uuid = ?"

        with self.db.transaction() as conn:
            conn.execute(sql, values)

        self._post_update(uuid_, old_data, data)
        return {**(old_data or {}), **data}

    def delete(self, uuid_: str) -> bool:
        """Permanently delete an entry by UUID.

        Returns:
            True if an entry was deleted.
        """
        old_data = self.get(uuid_)
        sql = f"DELETE FROM {self.table} WHERE uuid LIKE ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, (f"{uuid_}%",))
            deleted = cursor.rowcount > 0
        if deleted:
            self._post_delete(uuid_, old_data)
        return deleted

    def count(self) -> int:
        """Return the number of entries in the table."""
        row = self.db.execute_one(f"SELECT COUNT(*) AS cnt FROM {self.table}")
        return row["cnt"] if row else 0
