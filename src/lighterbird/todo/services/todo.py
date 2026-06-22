"""Todo CRUD service with formula-based priority and label management."""

from __future__ import annotations

from typing import Any

from lighterbird.core.crud import CRUDService
from lighterbird.core.priority import eval_safe, validate_safe


class TodoService(CRUDService):
    """CRUD service for taskoj (todos) with priority formulas and labels."""

    def __init__(self, db):
        super().__init__(db, "taskoj")

    # ── Search ──────────────────────────────────────────────────────────

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
        rows = self.db.execute(
            f"SELECT * FROM taskoj WHERE {where} ORDER BY kreita_je DESC LIMIT ?",
            (*params, limit),
        )
        # Compute effective priority for each row
        for row in rows:
            row["_computed_priority"] = self._compute_priority(row)
        return rows

    def list(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        rows = super().list(limit=limit, offset=offset)
        for row in rows:
            row["_computed_priority"] = self._compute_priority(row)
        return rows

    # ── Priority ────────────────────────────────────────────────────────

    def _compute_priority(self, todo: dict[str, Any]) -> float:
        """Compute effective priority from formula and creation time."""
        formula = str(todo.get("prioritato", "5") or "5")
        created_at = todo.get("kreita_je", "")
        if not created_at:
            return float(formula) if formula.replace(".", "").isdigit() else 5.0

        from datetime import datetime, timezone

        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return 5.0

        now = datetime.now(timezone.utc)
        delta = now - created.astimezone(timezone.utc)
        if delta.total_seconds() < 0:
            delta = delta  # use zero below

        context = {
            "M": delta.total_seconds() / (86400.0 * 30.0),
            "D": delta.total_seconds() / 86400.0,
            "H": delta.total_seconds() / 3600.0,
            "MIN": delta.total_seconds() / 60.0,
            "m": delta.total_seconds() / 60.0,
        }

        try:
            return eval_safe(formula, context)
        except (ValueError, ZeroDivisionError):
            return 5.0

    def validate_priority_formula(self, formula: str) -> bool:
        """Check if a priority formula is syntactically valid."""
        return validate_safe(formula)

    def mark_done(self, uuid_: str) -> bool:
        """Mark a todo as done."""
        result = self.update(uuid_, {"stato": "done"})
        return result is not None

    # ── Labels ──────────────────────────────────────────────────────────

    def add_label(self, todo_uuid: str, label_uuid: str) -> None:
        """Attach a label to a todo."""
        self.db.execute(
            "INSERT OR IGNORE INTO todoj_etikedo (todo_uuid, etikedo_uuid) VALUES (?, ?)",
            (todo_uuid, label_uuid),
        )

    def remove_label(self, todo_uuid: str, label_uuid: str) -> None:
        """Detach a label from a todo."""
        self.db.execute(
            "DELETE FROM todoj_etikedo WHERE todo_uuid = ? AND etikedo_uuid = ?",
            (todo_uuid, label_uuid),
        )

    def get_labels(self, todo_uuid: str) -> list[dict[str, Any]]:
        """Get all labels attached to a todo."""
        return self.db.execute(
            "SELECT e.* FROM etikedoj e "
            "JOIN todoj_etikedo te ON e.uuid = te.etikedo_uuid "
            "WHERE te.todo_uuid = ? ORDER BY e.teksto",
            (todo_uuid,),
        )

    def list_all_labels(self) -> list[dict[str, Any]]:
        """List all available labels."""
        return self.db.execute("SELECT * FROM etikedoj ORDER BY teksto")

    def create_label(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new label."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        import uuid

        label = {
            "uuid": str(uuid.uuid4()),
            "teksto": data.get("teksto", "").strip(),
            "koloro": data.get("koloro", ""),
            "kreita_je": now,
            "modifita_je": now,
        }
        if not label["teksto"]:
            raise ValueError("Label text (teksto) is required.")
        return self.db.execute_one(
            "INSERT INTO etikedoj (uuid, teksto, koloro, kreita_je, modifita_je) "
            "VALUES (?, ?, ?, ?, ?) RETURNING *",
            (label["uuid"], label["teksto"], label["koloro"], now, now),
        )

    def delete_label(self, label_uuid: str) -> None:
        """Delete a label and all its associations."""
        self.db.execute("DELETE FROM etikedoj WHERE uuid = ?", (label_uuid,))
