"""Message query service.

Flat service class, forked from A-lien's RetpostoMessagingMixin.
"""

from __future__ import annotations

from typing import Any


class MessageService:
    """Read-only message queries."""

    def __init__(self, db):
        self.db = db

    def get_message(self, uuid_: str) -> dict[str, Any] | None:
        """Get a non-deleted message by UUID."""
        return self.db.execute_one(
            "SELECT * FROM mesagoj WHERE uuid = ? AND forigita = 0", (uuid_,)
        )

    def find_by_uuid_prefix(self, prefix: str) -> list[dict[str, Any]]:
        """Find non-deleted messages by UUID prefix."""
        if not prefix:
            return []
        return list(
            self.db.execute(
                "SELECT * FROM mesagoj WHERE uuid LIKE ? AND forigita = 0",
                (f"{prefix}%",),
            )
        )

    def list_messages(
        self,
        konto_id: str | None = None,
        folder: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List non-deleted messages, optionally filtered."""
        conditions = ["m.forigita = 0"]
        params: list[Any] = []
        if konto_id:
            conditions.append("m.konto_id = ?")
            params.append(konto_id)
        if folder:
            conditions.append(
                "m.dosierujo_id IN (SELECT uuid FROM dosierujoj WHERE nomo = ?)"
            )
            params.append(folder)
        where = " AND ".join(conditions)
        sql = (
            "SELECT m.*, COALESCE(d.nomo, '') AS dosierujo_nomo"
            " FROM mesagoj m"
            " LEFT JOIN dosierujoj d ON m.dosierujo_id = d.uuid"
            f" WHERE {where}"
            " ORDER BY m.ricevita_je DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        return list(self.db.execute(sql, tuple(params)))

    def search_messages(
        self, filters: dict[str, Any], limit: int = 50
    ) -> list[dict[str, Any]]:
        """Search messages with filters."""
        conditions = ["m.forigita = 0"]
        params: list[Any] = []
        if filters.get("query"):
            conditions.append("(m.subjekto LIKE ? OR m.korpo LIKE ?)")
            q = f"%{filters['query']}%"
            params.extend([q, q])
        if filters.get("from"):
            conditions.append("m.de LIKE ?")
            params.append(f"%{filters['from']}%")
        if filters.get("to"):
            conditions.append("m.al LIKE ?")
            params.append(f"%{filters['to']}%")
        if filters.get("subject"):
            conditions.append("m.subjekto LIKE ?")
            params.append(f"%{filters['subject']}%")
        if filters.get("body"):
            conditions.append("m.korpo LIKE ?")
            params.append(f"%{filters['body']}%")
        if filters.get("after"):
            conditions.append("m.ricevita_je >= ?")
            params.append(filters["after"])
        if filters.get("before"):
            conditions.append("m.ricevita_je <= ?")
            params.append(filters["before"])
        if filters.get("read") is not None:
            conditions.append("m.legita = ?")
            params.append(1 if filters["read"] else 0)
        if filters.get("account"):
            conditions.append("m.konto_id = ?")
            params.append(filters["account"])
        if filters.get("folder"):
            conditions.append(
                "m.dosierujo_id IN (SELECT uuid FROM dosierujoj WHERE nomo = ?)"
            )
            params.append(filters["folder"])
        where = " AND ".join(conditions)
        sql = (
            "SELECT m.*, COALESCE(d.nomo, '') AS dosierujo_nomo"
            " FROM mesagoj m"
            " LEFT JOIN dosierujoj d ON m.dosierujo_id = d.uuid"
            f" WHERE {where}"
            " ORDER BY m.ricevita_je DESC LIMIT ?"
        )
        params.append(limit)
        try:
            rows = self.db.execute(sql, tuple(params))
        except Exception:
            fallback_sql = (
                "SELECT m.*, '' AS dosierujo_nomo"
                " FROM mesagoj m"
                " WHERE m.forigita = 0"
                " ORDER BY m.ricevita_je DESC LIMIT ?"
            )
            rows = self.db.execute(fallback_sql, (limit,))
        return list(rows)
