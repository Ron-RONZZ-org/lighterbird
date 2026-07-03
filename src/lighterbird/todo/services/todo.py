"""Todo CRUD service with formula-based priority, label management,
subtask hierarchy, dependencies, file attachments, and templates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from lighterbird.core.crud import CRUDService
from lighterbird.core.priority import eval_safe, validate_safe


class TodoService(CRUDService):
    """CRUD service for tasks with priority formulas, labels,
    subtask hierarchy, dependencies, attachments, and templates."""

    def __init__(self, db):
        super().__init__(db, "tasks")

    # ── Search & List ───────────────────────────────────────────────────

    def search(self, query: str, status: str | None = None,
               limit: int = 50, tags: list[str] | None = None,
               sort: str | None = None) -> list[dict[str, Any]]:
        if not query and not status and not tags:
            return self.list(limit=limit, sort=sort)
        joins: list[str] = []
        conditions: list[str] = []
        params: list[Any] = []
        group_by = None
        having = None

        if query:
            conditions.append("(LOWER(t.title) LIKE LOWER(?)"
                               " OR LOWER(t.description) LIKE LOWER(?))")
            params.extend([f"%{query}%", f"%{query}%"])
        if status:
            conditions.append("t.status = ?")
            params.append(status)
        if tags:
            joins.append("JOIN todo_labels tl ON t.uuid = tl.todo_uuid")
            placeholders = ",".join("?" for _ in tags)
            conditions.append(f"tl.label_name IN ({placeholders})")
            params.extend(tags)
            group_by = "t.uuid"
            having = f"COUNT(DISTINCT tl.label_name) = {len(tags)}"

        # Sort order
        sort_map = {
            "priority": "CAST(t.priority AS INTEGER) DESC",
            "due": "t.due_date ASC NULLS LAST",
            "title": "t.title ASC",
            "created": "t.created_at DESC",
        }
        order_by = sort_map.get(sort or "", "t.created_at DESC")

        where = " AND ".join(conditions) if conditions else "1=1"
        group_clause = f" GROUP BY {group_by}" if group_by else ""
        having_clause = f" HAVING {having}" if having else ""
        sql = (
            f"SELECT t.* FROM tasks t"
            f" {' '.join(joins)}"
            f" WHERE {where}"
            f"{group_clause}{having_clause}"
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

    # ── Labels batch fetch ──────────────────────────────────────────────

    def _attach_labels(self, todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Batch-attach label info to each todo in the list."""
        if not todos:
            return todos
        uuids = [t["uuid"] for t in todos]
        placeholders = ",".join("?" for _ in uuids)
        rows = self.db.execute(
            f"SELECT tl.todo_uuid, l.name, l.color"
            f" FROM todo_labels tl"
            f" JOIN labels l ON tl.label_name = l.name"
            f" WHERE tl.todo_uuid IN ({placeholders})",
            uuids,
        )
        label_map: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            label_map.setdefault(row["todo_uuid"], []).append(
                {"name": row["name"], "color": row["color"]},
            )
        for t in todos:
            t["labels"] = label_map.get(t["uuid"], [])
        return todos

    # ── Tree / Hierarchy ────────────────────────────────────────────────

    def get_tree(self, parent_uuid: str | None = None,
                 depth: int = 0, max_depth: int = 10
                 ) -> list[dict[str, Any]]:
        if depth > max_depth:
            return []
        if parent_uuid is None:
            rows = self.db.execute(
                "SELECT * FROM tasks WHERE parent_uuid IS NULL"
                " ORDER BY sort_order, created_at DESC",
            )
        else:
            rows = self.db.execute(
                "SELECT * FROM tasks WHERE parent_uuid = ?"
                " ORDER BY sort_order, created_at DESC",
                (parent_uuid,),
            )
        result = []
        for row in rows:
            children = self.get_tree(row["uuid"], depth + 1, max_depth)
            item = dict(row)
            item["children"] = children
            item["_computed_priority"] = self._compute_priority(item)
            result.append(item)
        return result

    def flatten_tree(self, parent_uuid: str | None = None) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []

        def _walk(pid: str | None, depth: int) -> None:
            if pid is None:
                rows = self.db.execute(
                    "SELECT * FROM tasks WHERE parent_uuid IS NULL"
                    " ORDER BY sort_order, created_at DESC",
                )
            else:
                rows = self.db.execute(
                    "SELECT * FROM tasks WHERE parent_uuid = ?"
                    " ORDER BY sort_order, created_at DESC",
                    (pid,),
                )
            for row in rows:
                has_children = bool(
                    self.db.execute_one(
                        "SELECT 1 FROM tasks WHERE parent_uuid = ? LIMIT 1",
                        (row["uuid"],),
                    )
                )
                item = dict(row)
                item["_depth"] = depth
                item["_has_children"] = has_children
                item["_computed_priority"] = self._compute_priority(item)
                flat.append(item)
                if has_children:
                    _walk(row["uuid"], depth + 1)

        _walk(parent_uuid, 0)
        return self._attach_labels(flat)

    def get_with_children(self, uuid_: str) -> dict[str, Any] | None:
        todo = self.get(uuid_)
        if not todo:
            return None
        todo["children"] = self.get_tree(uuid_, depth=1)
        todo["_computed_priority"] = self._compute_priority(todo)
        todo["labels"] = self.get_labels(uuid_)
        return todo

    def move_as_child(self, uuid_: str, parent_uuid_: str | None) -> None:
        self.update(uuid_, {"parent_uuid": parent_uuid_})

    # ── Override hooks ──────────────────────────────────────────────────

    def _post_delete(self, uuid_: str, data: dict[str, Any] | None) -> None:
        """Reparent children when a todo is deleted (not cascade)."""
        if data:
            children = self.db.execute(
                "SELECT uuid FROM tasks WHERE parent_uuid = ?",
                (uuid_,),
            )
            grandparent = data.get("parent_uuid")
            for child in children:
                self.db.execute(
                    "UPDATE tasks SET parent_uuid = ? WHERE uuid = ?",
                    (grandparent, child["uuid"]),
                )

    def _post_update(
        self, uuid_: str, old_data: dict[str, Any] | None,
        new_data: dict[str, Any],
    ) -> None:
        """Handle tag updates after a normal update."""
        tags = new_data.pop("_tags", None)
        if tags is not None:
            # Remove existing labels, then add new ones
            current = self.db.execute(
                "SELECT label_name FROM todo_labels WHERE todo_uuid = ?",
                (uuid_,),
            )
            for row in current:
                self.db.execute(
                    "DELETE FROM todo_labels WHERE todo_uuid = ? AND label_name = ?",
                    (uuid_, row["label_name"]),
                )
            for tag_name in tags:
                self.add_label(uuid_, tag_name)

    def _post_create(self, data: dict[str, Any], result: dict[str, Any]) -> None:
        """Handle dependency and tag setup after creation."""
        depends_on = data.pop("_depends_on", None)
        if depends_on:
            now = datetime.now(timezone.utc).isoformat()
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
        now = datetime.now(timezone.utc).isoformat()
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
        now = datetime.now(timezone.utc).isoformat()
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
        now = datetime.now(timezone.utc).isoformat()
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

        from datetime import datetime, timezone

        try:
            created = datetime.fromisoformat(
                created_at.replace("Z", "+00:00"),
            )
        except (ValueError, TypeError):
            return 5.0

        now = datetime.now(timezone.utc)
        delta = now - created.astimezone(timezone.utc)

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
        return validate_safe(formula)

    # ── Status ──────────────────────────────────────────────────────────

    def mark_done(self, uuid_: str) -> bool:
        result = self.update(uuid_, {"status": "done"})
        return result is not None

    # ── Labels ──────────────────────────────────────────────────────────

    def add_label(self, todo_uuid: str, label_name: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO todo_labels"
            " (todo_uuid, label_name) VALUES (?, ?)",
            (todo_uuid, label_name),
        )

    def remove_label(self, todo_uuid: str, label_name: str) -> None:
        self.db.execute(
            "DELETE FROM todo_labels"
            " WHERE todo_uuid = ? AND label_name = ?",
            (todo_uuid, label_name),
        )

    def get_labels(self, todo_uuid: str) -> list[dict[str, Any]]:
        return self.db.execute(
            "SELECT l.* FROM labels l"
            " JOIN todo_labels tl ON l.name = tl.label_name"
            " WHERE tl.todo_uuid = ? ORDER BY l.name",
            (todo_uuid,),
        )

    def list_all_labels(self) -> list[dict[str, Any]]:
        return self.db.execute("SELECT * FROM labels ORDER BY name")

    def create_label(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        name = data.get("name", "").strip()
        if not name:
            raise ValueError("Label name is required.")
        color = data.get("color", "")
        try:
            return self.db.execute_one(
                "INSERT INTO labels (name, color, created_at, updated_at)"
                " VALUES (?, ?, ?, ?) RETURNING *",
                (name, color, now, now),
            )
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError(
                    f"Label '{name}' already exists.",
                ) from e
            raise

    def delete_label(self, label_uuid: str) -> None:
        self.db.execute(
            "DELETE FROM labels WHERE uuid = ?", (label_uuid,),
        )

    # ── Templates ───────────────────────────────────────────────────────

    def create_template(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        tpl_uuid = str(uuid.uuid4())
        name = data.get("name", "").strip()
        if not name:
            raise ValueError("Template name is required.")
        title_placeholder = data.get("title_placeholder", "")
        self.db.execute(
            "INSERT INTO templates (uuid, name, title_placeholder,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (tpl_uuid, name, title_placeholder, now, now),
        )
        fields = data.get("fields", [])
        for i, f in enumerate(fields):
            field_uuid = str(uuid.uuid4())
            field_name = f.get("name", "").strip()
            is_required = field_name.startswith("!")
            if is_required:
                field_name = field_name[1:].strip()
            if not field_name:
                continue
            self.db.execute(
                "INSERT INTO template_fields"
                " (uuid, template_uuid, field_name, field_type,"
                "  is_required, sort_order)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (field_uuid, tpl_uuid, field_name,
                 f.get("type", "text"), 1 if is_required else 0, i),
            )
        return self.get_template(tpl_uuid)

    def get_template(self, uuid_: str) -> dict[str, Any] | None:
        tpl = self.db.execute_one(
            "SELECT * FROM templates WHERE uuid = ?", (uuid_,),
        )
        if not tpl:
            return None
        tpl["fields"] = self.db.execute(
            "SELECT * FROM template_fields WHERE template_uuid = ?"
            " ORDER BY sort_order", (uuid_,),
        )
        return tpl

    def get_template_by_name(self, name: str) -> dict[str, Any] | None:
        tpl = self.db.execute_one(
            "SELECT * FROM templates WHERE name = ?", (name,),
        )
        if not tpl:
            return None
        tpl["fields"] = self.db.execute(
            "SELECT * FROM template_fields WHERE template_uuid = ?"
            " ORDER BY sort_order", (tpl["uuid"],),
        )
        return tpl

    def list_templates(self) -> list[dict[str, Any]]:
        return self.db.execute(
            "SELECT * FROM templates ORDER BY name",
        )

    def update_template(self, uuid_: str,
                        data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        if "name" in data:
            self.db.execute(
                "UPDATE templates SET name = ?, updated_at = ?"
                " WHERE uuid = ?",
                (data["name"], now, uuid_),
            )
        if "title_placeholder" in data:
            self.db.execute(
                "UPDATE templates SET title_placeholder = ?,"
                " updated_at = ? WHERE uuid = ?",
                (data["title_placeholder"], now, uuid_),
            )
        if "fields" in data:
            self.db.execute(
                "DELETE FROM template_fields WHERE template_uuid = ?",
                (uuid_,),
            )
            for i, f in enumerate(data["fields"]):
                field_uuid = str(uuid.uuid4())
                field_name = f.get("name", "").strip()
                is_required = field_name.startswith("!")
                if is_required:
                    field_name = field_name[1:].strip()
                if not field_name:
                    continue
                self.db.execute(
                    "INSERT INTO template_fields"
                    " (uuid, template_uuid, field_name, field_type,"
                    "  is_required, sort_order)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (field_uuid, uuid_, field_name,
                     f.get("type", "text"), 1 if is_required else 0, i),
                )
        self.db.execute(
            "UPDATE templates SET updated_at = ? WHERE uuid = ?",
            (now, uuid_),
        )
        return self.get_template(uuid_)

    def delete_template(self, uuid_: str) -> None:
        self.db.execute(
            "DELETE FROM templates WHERE uuid = ?", (uuid_,),
        )

    def template_fields_in_use(self, template_uuid: str
                                ) -> dict[str, int]:
        tpl = self.get_template(template_uuid)
        if not tpl:
            return {}
        result: dict[str, int] = {}
        todos = self.db.execute(
            "SELECT uuid FROM tasks WHERE template_uuid = ?",
            (template_uuid,),
        )
        if not todos:
            return {}
        for field in tpl.get("fields", []):
            count = 0
            for todo in todos:
                desc = self.db.execute_one(
                    "SELECT description FROM tasks WHERE uuid = ?",
                    (todo["uuid"],),
                )
                if desc and desc.get("description"):
                    import json
                    try:
                        tpl_data = json.loads(desc["description"])
                        if isinstance(tpl_data, dict):
                            val = tpl_data.get(field["field_name"], "")
                            if val:
                                count += 1
                    except (json.JSONDecodeError, TypeError):
                        pass
            if count > 0:
                result[field["field_name"]] = count
        return result
