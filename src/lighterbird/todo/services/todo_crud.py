"""CRUD-heavy mixin: search, list, labels, dependencies, attachments, priority."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from lighterbird.core.priority import eval_safe, validate_safe
from lighterbird.tags.service import TagService


class _TodoCrudMixin:
    """Mixin providing CRUD operations, labels, dependencies, and attachments
    for the TodoService class."""

    def _tag_svc(self) -> TagService:
        """Lazy-initialised TagService for cross-domain tag management."""
        svc = getattr(self, "_tag_service", None)
        if svc is None:
            svc = TagService()
            self._tag_service = svc  # type: ignore[attr-defined]
        return svc

    # ── Search & List ───────────────────────────────────────────────────

    def search(self, query: str, status: str | None = None,
               limit: int = 50, tags: list[str] | None = None,
               sort: str | None = None) -> list[dict[str, Any]]:
        if not query and not status and not tags:
            return self.list(limit=limit, sort=sort)
        conditions: list[str] = []
        params: list[Any] = []

        if query:
            conditions.append("(LOWER(t.title) LIKE LOWER(?)"
                               " OR LOWER(t.description) LIKE LOWER(?))")
            params.extend([f"%{query}%", f"%{query}%"])
        if status:
            conditions.append("t.status = ?")
            params.append(status)
        if tags:
            # Look up todo UUIDs that have ALL specified tags via the shared tag system
            tag_svc = self._tag_svc()
            tag_uuids: set[str] | None = None
            for tag_name in tags:
                items = set(
                    r["item_uuid"]
                    for r in tag_svc.db.execute(
                        "SELECT item_uuid FROM taggings"
                        " WHERE domain = 'todo' AND tag_name = ?",
                        (tag_name,),
                    )
                )
                if tag_uuids is None:
                    tag_uuids = items
                else:
                    tag_uuids &= items
            if tag_uuids is not None and len(tag_uuids) > 0:
                placeholders = ",".join("?" for _ in tag_uuids)
                conditions.append(f"t.uuid IN ({placeholders})")
                params.extend(tag_uuids)
            elif tag_uuids is not None:
                # No tasks match the tag intersection; return empty
                return []

        # Sort order
        sort_map = {
            "priority": "CAST(t.priority AS INTEGER) DESC",
            "due": "t.due_date ASC NULLS LAST",
            "title": "t.title ASC",
            "created": "t.created_at DESC",
        }
        order_by = sort_map.get(sort or "", "t.created_at DESC")

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = (
            f"SELECT t.* FROM tasks t"
            f" WHERE {where}"
            f" ORDER BY {order_by} LIMIT ?"
        )
        rows = list(self.db.execute(sql, (*params, limit)))
        for row in rows:
            row["_computed_priority"] = self._compute_priority(row)
        return self._attach_labels(rows)

    def search_titles(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search by title only — for autocomplete dropdowns."""
        if not query:
            return []
        rows = self.db.execute(
            "SELECT uuid, title FROM tasks WHERE LOWER(title)"
            " LIKE LOWER(?) ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", limit),
        )
        return rows

    def list(self, limit: int = 100, offset: int = 0,
             sort: str | None = None) -> list[dict[str, Any]]:
        sort_map = {
            "priority": "CAST(priority AS INTEGER) DESC",
            "due": "due_date ASC NULLS LAST",
            "title": "title ASC",
            "created": "created_at DESC",
        }
        order_by = sort_map.get(sort or "", "created_at DESC")
        rows = list(self.db.execute(
            f"SELECT * FROM tasks ORDER BY {order_by} LIMIT ? OFFSET ?",
            (limit, offset),
        ))
        for row in rows:
            row["_computed_priority"] = self._compute_priority(row)
        return self._attach_labels(rows)

    # ── Labels batch fetch (via shared tag system) ──────────────────────

    def _attach_labels(self, todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Batch-attach label info to each todo from the shared tag system."""
        if not todos:
            return todos
        tag_svc = self._tag_svc()
        uuid_map: dict[str, list[dict[str, str]]] = {}
        for t in todos:
            uid = t["uuid"]
            labels = tag_svc.get_tags_for("todo", uid)
            if labels:
                uuid_map[uid] = [{"name": l["name"], "color": l["color"]} for l in labels]
        for t in todos:
            t["labels"] = uuid_map.get(t["uuid"], [])
        return todos

    # ── Override hooks ──────────────────────────────────────────────────

    def delete(self, uuid_: str, soft: bool = True) -> bool:
        """Delete a todo, reparenting children to grandparent first.

        We must reparent *before* the DELETE runs because the FK constraint
        ``ON DELETE SET NULL`` would nullify ``parent_uuid`` on children,
        making it impossible to find them afterward.
        """
        old_data = self.get(uuid_)
        if not old_data:
            return False
        children = list(self.db.execute(
            "SELECT uuid FROM tasks WHERE parent_uuid = ?",
            (uuid_,),
        ))
        grandparent = old_data.get("parent_uuid")
        # Do the actual delete (FK SET NULL fires here)
        result = super().delete(uuid_, soft=soft)
        if result and children and grandparent is not None:
            for child in children:
                self.db.execute(
                    "UPDATE tasks SET parent_uuid = ? WHERE uuid = ?",
                    (grandparent, child["uuid"]),
                )
        return result

    def _post_update(
        self, uuid_: str, old_data: dict[str, Any] | None,
        new_data: dict[str, Any],
    ) -> None:
        """Handle tag updates after a normal update."""
        tags = new_data.pop("_tags", None)
        if tags is not None:
            self._tag_svc().set_tags("todo", uuid_, tags)

    def _post_create(self, data: dict[str, Any], result: dict[str, Any]) -> None:
        """Handle dependency and tag setup after creation."""
        depends_on = data.pop("_depends_on", None)
        if depends_on:
            now = datetime.now(UTC).isoformat()
            dep_list = depends_on if isinstance(depends_on, list) else [depends_on]
            for dep_uuid in dep_list:
                if dep_uuid:
                    self.db.execute(
                        "INSERT OR IGNORE INTO todo_dependencies"
                        " (task_uuid, depends_on, type, created_at)"
                        " VALUES (?, ?, 'blocked_by', ?)",
                        (result["uuid"], dep_uuid, now),
                    )
        tags = data.pop("_tags", None)
        if tags:
            for tag_name in tags:
                self.add_label(result["uuid"], tag_name)

    # ── Dependencies ────────────────────────────────────────────────────

    def add_dependency(self, task_uuid: str, depends_on_uuid: str) -> None:
        if task_uuid == depends_on_uuid:
            raise ValueError("A task cannot depend on itself.")
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "INSERT OR IGNORE INTO todo_dependencies"
            " (task_uuid, depends_on, type, created_at)"
            " VALUES (?, ?, 'blocked_by', ?)",
            (task_uuid, depends_on_uuid, now),
        )

    def remove_dependency(self, task_uuid: str, depends_on_uuid: str) -> None:
        self.db.execute(
            "DELETE FROM todo_dependencies"
            " WHERE task_uuid = ? AND depends_on = ?",
            (task_uuid, depends_on_uuid),
        )

    def get_dependencies(self, task_uuid: str) -> list[dict[str, Any]]:
        return self.db.execute(
            "SELECT t.* FROM tasks t"
            " JOIN todo_dependencies d ON t.uuid = d.depends_on"
            " WHERE d.task_uuid = ?",
            (task_uuid,),
        )

    def get_blocked_tasks(self, task_uuid: str) -> list[dict[str, Any]]:
        return self.db.execute(
            "SELECT t.* FROM tasks t"
            " JOIN todo_dependencies d ON t.uuid = d.task_uuid"
            " WHERE d.depends_on = ?",
            (task_uuid,),
        )

    # ── Attachments ─────────────────────────────────────────────────────

    def add_attachment(self, todo_uuid: str,
                       original_name: str,
                       original_path: str = "",
                       cache_path: str = "",
                       mime_type: str = "",
                       size: int = 0,
                       md5_checksum: str = "") -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        att_uuid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO attachments"
            " (uuid, todo_uuid, original_name, original_path,"
            "  cache_path, mime_type, size, md5_checksum,"
            "  created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (att_uuid, todo_uuid, original_name, original_path,
             cache_path, mime_type, size, md5_checksum,
             now, now),
        )
        return self.db.execute_one(
            "SELECT * FROM attachments WHERE uuid = ?", (att_uuid,),
        )

    def remove_attachment(self, attachment_uuid: str) -> None:
        self.db.execute(
            "DELETE FROM attachments WHERE uuid = ?", (attachment_uuid,),
        )

    def get_attachments(self, todo_uuid: str) -> list[dict[str, Any]]:
        return self.db.execute(
            "SELECT * FROM attachments WHERE todo_uuid = ?"
            " ORDER BY created_at", (todo_uuid,),
        )

    def get_attachments_needing_sync(self) -> list[dict[str, Any]]:
        return self.db.execute(
            "SELECT * FROM attachments"
            " WHERE original_path LIKE 'http%'"
            " AND sync_status != 'synced'",
        )

    def mark_attachment_synced(self, attachment_uuid: str,
                               md5_checksum: str = "") -> None:
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "UPDATE attachments SET sync_status = 'synced',"
            " md5_checksum = ?, last_synced_at = ?, updated_at = ?"
            " WHERE uuid = ?",
            (md5_checksum, now, now, attachment_uuid),
        )

    # ── Priority ────────────────────────────────────────────────────────

    def _compute_priority(self, todo: dict[str, Any]) -> float:
        formula = str(todo.get("priority", "5") or "5")
        created_at = todo.get("created_at", "")
        if not created_at:
            return float(formula) if formula.replace(".", "").isdigit() else 5.0

        from datetime import datetime

        try:
            created = datetime.fromisoformat(
                created_at.replace("Z", "+00:00"),
            )
        except (ValueError, TypeError):
            return 5.0

        now = datetime.now(UTC)
        delta = now - created.astimezone(UTC)

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
        return validate_safe(formula, allowed_vars={"M", "D", "H", "MIN", "m"})

    # ── Status ──────────────────────────────────────────────────────────

    def mark_done(self, uuid_: str) -> bool:
        result = self.update(uuid_, {"status": "done"})
        return result is not None

    # ── Labels (via shared tag system) ──────────────────────────────────

    def add_label(self, todo_uuid: str, label_name: str) -> None:
        self._tag_svc().add_tag("todo", todo_uuid, label_name)

    def remove_label(self, todo_uuid: str, label_name: str) -> None:
        self._tag_svc().remove_tag("todo", todo_uuid, label_name)

    def get_labels(self, todo_uuid: str) -> list[dict[str, Any]]:
        return self._tag_svc().get_tags_for("todo", todo_uuid)

    def list_all_labels(self) -> list[dict[str, Any]]:
        return self._tag_svc().list_tags()

    def create_label(self, data: dict[str, Any]) -> dict[str, Any]:
        return self._tag_svc().create_tag(
            name=data.get("name", ""),
            color=data.get("color", ""),
        )

    def delete_label(self, label_name: str) -> None:
        self._tag_svc().delete_tag(label_name)
