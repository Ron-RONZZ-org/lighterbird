"""Todo CRUD service with formula-based priority, label management,
subtask hierarchy, dependencies, file attachments, and templates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from lighterbird.core.crud import CRUDService
from lighterbird.core.priority import eval_safe, validate_safe


class TodoService(CRUDService):
    """CRUD service for taskoj (todos) with priority formulas, labels,
    subtask hierarchy, dependencies, attachments, and templates."""

    def __init__(self, db):
        super().__init__(db, "taskoj")

    # ── Search & List ───────────────────────────────────────────────────

    def search(self, query: str, status: str | None = None, limit: int = 50
               ) -> list[dict[str, Any]]:
        if not query and not status:
            return self.list(limit=limit)
        conditions: list[str] = []
        params: list[Any] = []
        if query:
            conditions.append("(LOWER(titolo) LIKE LOWER(?)"
                              " OR LOWER(priskribo) LIKE LOWER(?))")
            params.extend([f"%{query}%", f"%{query}%"])
        if status:
            conditions.append("stato = ?")
            params.append(status)
        where = " AND ".join(conditions)
        rows = self.db.execute(
            f"SELECT * FROM taskoj WHERE {where} ORDER BY"
            f" kreita_je DESC LIMIT ?",
            (*params, limit),
        )
        for row in rows:
            row["_computed_priority"] = self._compute_priority(row)
        return rows

    def search_titles(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search by title only — for autocomplete dropdowns."""
        if not query:
            return []
        rows = self.db.execute(
            "SELECT uuid, titolo FROM taskoj WHERE LOWER(titolo)"
            " LIKE LOWER(?) ORDER BY kreita_je DESC LIMIT ?",
            (f"%{query}%", limit),
        )
        return rows

    def list(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        rows = super().list(limit=limit, offset=offset)
        for row in rows:
            row["_computed_priority"] = self._compute_priority(row)
        return rows

    # ── Tree / Hierarchy ────────────────────────────────────────────────

    def get_tree(self, parent_uuid: str | None = None,
                 depth: int = 0, max_depth: int = 10
                 ) -> list[dict[str, Any]]:
        """Recursively build a tree of todos.

        If parent_uuid is None, return root-level items
        (those with parent_uuid IS NULL).
        """
        if depth > max_depth:
            return []
        if parent_uuid is None:
            rows = self.db.execute(
                "SELECT * FROM taskoj WHERE parent_uuid IS NULL"
                " ORDER BY sort_order, kreita_je DESC",
            )
        else:
            rows = self.db.execute(
                "SELECT * FROM taskoj WHERE parent_uuid = ?"
                " ORDER BY sort_order, kreita_je DESC",
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
        """Return a flat list with depth metadata for frontend tree view."""
        flat: list[dict[str, Any]] = []

        def _walk(pid: str | None, depth: int) -> None:
            if pid is None:
                rows = self.db.execute(
                    "SELECT * FROM taskoj WHERE parent_uuid IS NULL"
                    " ORDER BY sort_order, kreita_je DESC",
                )
            else:
                rows = self.db.execute(
                    "SELECT * FROM taskoj WHERE parent_uuid = ?"
                    " ORDER BY sort_order, kreita_je DESC",
                    (pid,),
                )
            for row in rows:
                has_children = bool(
                    self.db.execute_one(
                        "SELECT 1 FROM taskoj WHERE parent_uuid = ? LIMIT 1",
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
        return flat

    def get_with_children(self, uuid_: str) -> dict[str, Any] | None:
        """Get a todo with its children nested inside."""
        todo = self.get(uuid_)
        if not todo:
            return None
        todo["children"] = self.get_tree(uuid_, depth=1)
        todo["_computed_priority"] = self._compute_priority(todo)
        return todo

    def move_as_child(self, uuid_: str, parent_uuid_: str | None) -> None:
        """Move a todo under a new parent (or to root if parent is None)."""
        self.update(uuid_, {"parent_uuid": parent_uuid_})

    # ── Override hooks ──────────────────────────────────────────────────

    def _post_delete(self, uuid_: str, data: dict[str, Any] | None) -> None:
        """Reparent children when a todo is deleted (not cascade)."""
        if data:
            children = self.db.execute(
                "SELECT uuid FROM taskoj WHERE parent_uuid = ?",
                (uuid_,),
            )
            grandparent = data.get("parent_uuid")
            for child in children:
                self.db.execute(
                    "UPDATE taskoj SET parent_uuid = ? WHERE uuid = ?",
                    (grandparent, child["uuid"]),
                )

    def _post_create(self, data: dict[str, Any], result: dict[str, Any]) -> None:
        """Handle dependency setup after creation."""
        depends_on = data.pop("_depends_on", None)
        if depends_on:
            now = datetime.now(timezone.utc).isoformat()
            for dep_uuid in (depends_on if isinstance(depends_on, list)
                             else [depends_on]):
                self.db.execute(
                    "INSERT OR IGNORE INTO todoj_dependoj"
                    " (task_uuid, dependanta_je, type, kreita_je)"
                    " VALUES (?, ?, 'blocked_by', ?)",
                    (result["uuid"], dep_uuid, now),
                )

    # ── Dependencies ────────────────────────────────────────────────────

    def add_dependency(self, task_uuid: str, depends_on_uuid: str) -> None:
        """Declare that task_uuid depends on depends_on_uuid."""
        if task_uuid == depends_on_uuid:
            raise ValueError("A task cannot depend on itself.")
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT OR IGNORE INTO todoj_dependoj"
            " (task_uuid, dependanta_je, type, kreita_je)"
            " VALUES (?, ?, 'blocked_by', ?)",
            (task_uuid, depends_on_uuid, now),
        )

    def remove_dependency(self, task_uuid: str, depends_on_uuid: str) -> None:
        """Remove a dependency."""
        self.db.execute(
            "DELETE FROM todoj_dependoj"
            " WHERE task_uuid = ? AND dependanta_je = ?",
            (task_uuid, depends_on_uuid),
        )

    def get_dependencies(self, task_uuid: str) -> list[dict[str, Any]]:
        """Get all tasks that this task depends on (blockers)."""
        return self.db.execute(
            "SELECT t.* FROM taskoj t"
            " JOIN todoj_dependoj d ON t.uuid = d.dependanta_je"
            " WHERE d.task_uuid = ?",
            (task_uuid,),
        )

    def get_blocked_tasks(self, task_uuid: str) -> list[dict[str, Any]]:
        """Get all tasks that depend on this task (blocked tasks)."""
        return self.db.execute(
            "SELECT t.* FROM taskoj t"
            " JOIN todoj_dependoj d ON t.uuid = d.task_uuid"
            " WHERE d.dependanta_je = ?",
            (task_uuid,),
        )

    # ── Attachments ─────────────────────────────────────────────────────

    def add_attachment(self, todo_uuid: str,
                       origina_nomo: str,
                       origina_vojo: str = "",
                       kasko_vojo: str = "",
                       dosier_peco: str = "",
                       grandeco: int = 0,
                       md5_cheksumo: str = "") -> dict[str, Any]:
        """Attach a file reference to a todo."""
        now = datetime.now(timezone.utc).isoformat()
        att_uuid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO aldonajxoj"
            " (uuid, todo_uuid, origina_nomo, origina_vojo,"
            "  kasko_vojo, dosier_peco, grandeco, md5_cheksumo,"
            "  kreita_je, modifita_je)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (att_uuid, todo_uuid, origina_nomo, origina_vojo,
             kasko_vojo, dosier_peco, grandeco, md5_cheksumo,
             now, now),
        )
        return self.db.execute_one(
            "SELECT * FROM aldonajxoj WHERE uuid = ?", (att_uuid,),
        )

    def remove_attachment(self, attachment_uuid: str) -> None:
        """Remove an attachment record."""
        self.db.execute(
            "DELETE FROM aldonajxoj WHERE uuid = ?", (attachment_uuid,),
        )

    def get_attachments(self, todo_uuid: str) -> list[dict[str, Any]]:
        """Get all attachments for a todo."""
        return self.db.execute(
            "SELECT * FROM aldonajxoj WHERE todo_uuid = ?"
            " ORDER BY kreita_je", (todo_uuid,),
        )

    def get_attachments_needing_sync(self) -> list[dict[str, Any]]:
        """Get all attachments needing sync (files from URLs)."""
        return self.db.execute(
            "SELECT * FROM aldonajxoj"
            " WHERE origina_vojo LIKE 'http%'"
            " AND sync_stato != 'synced'",
        )

    def mark_attachment_synced(self, attachment_uuid: str,
                               md5_cheksumo: str = "") -> None:
        """Mark an attachment as synced."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE aldonajxoj SET sync_stato = 'synced',"
            " md5_cheksumo = ?, last_sync_je = ?, modifita_je = ?"
            " WHERE uuid = ?",
            (md5_cheksumo, now, now, attachment_uuid),
        )

    # ── Priority ────────────────────────────────────────────────────────

    def _compute_priority(self, todo: dict[str, Any]) -> float:
        """Compute effective priority from formula and creation time."""
        formula = str(todo.get("prioritato", "5") or "5")
        created_at = todo.get("kreita_je", "")
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
        """Check if a priority formula is syntactically valid."""
        return validate_safe(formula)

    # ── Status ──────────────────────────────────────────────────────────

    def mark_done(self, uuid_: str) -> bool:
        """Mark a todo as done."""
        result = self.update(uuid_, {"stato": "done"})
        return result is not None

    # ── Labels ──────────────────────────────────────────────────────────

    def add_label(self, todo_uuid: str, label_teksto: str) -> None:
        """Attach a label to a todo."""
        self.db.execute(
            "INSERT OR IGNORE INTO todoj_etikedo"
            " (todo_uuid, etikedo_teksto) VALUES (?, ?)",
            (todo_uuid, label_teksto),
        )

    def remove_label(self, todo_uuid: str, label_teksto: str) -> None:
        """Detach a label from a todo."""
        self.db.execute(
            "DELETE FROM todoj_etikedo"
            " WHERE todo_uuid = ? AND etikedo_teksto = ?",
            (todo_uuid, label_teksto),
        )

    def get_labels(self, todo_uuid: str) -> list[dict[str, Any]]:
        """Get all labels attached to a todo."""
        return self.db.execute(
            "SELECT e.* FROM etikedoj e"
            " JOIN todoj_etikedo te ON e.teksto = te.etikedo_teksto"
            " WHERE te.todo_uuid = ? ORDER BY e.teksto",
            (todo_uuid,),
        )

    def list_all_labels(self) -> list[dict[str, Any]]:
        """List all available labels."""
        return self.db.execute("SELECT * FROM etikedoj ORDER BY teksto")

    def create_label(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new label."""
        now = datetime.now(timezone.utc).isoformat()
        teksto = data.get("teksto", "").strip()
        if not teksto:
            raise ValueError("Label text (teksto) is required.")
        koloro = data.get("koloro", "")
        try:
            return self.db.execute_one(
                "INSERT INTO etikedoj (teksto, koloro, kreita_je, modifita_je)"
                " VALUES (?, ?, ?, ?) RETURNING *",
                (teksto, koloro, now, now),
            )
        except Exception as e:
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                raise ValueError(
                    f"Label '{teksto}' already exists.",
                ) from e
            raise

    def delete_label(self, label_uuid: str) -> None:
        """Delete a label and all its associations."""
        self.db.execute(
            "DELETE FROM etikedoj WHERE uuid = ?", (label_uuid,),
        )

    # ── Templates ───────────────────────────────────────────────────────

    def create_template(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a template with optional fields."""
        now = datetime.now(timezone.utc).isoformat()
        tpl_uuid = str(uuid.uuid4())
        nomo = data.get("nomo", "").strip()
        if not nomo:
            raise ValueError("Template name (nomo) is required.")
        title_placeholder = data.get("title_placeholder", "")
        self.db.execute(
            "INSERT INTO shablonoj (uuid, nomo, title_placeholder,"
            " kreita_je, modifita_je) VALUES (?, ?, ?, ?, ?)",
            (tpl_uuid, nomo, title_placeholder, now, now),
        )
        fields = data.get("fields", [])
        for i, f in enumerate(fields):
            field_uuid = str(uuid.uuid4())
            kampo_nomo = f.get("nomo", "").strip()
            is_required = kampo_nomo.startswith("!")
            if is_required:
                kampo_nomo = kampo_nomo[1:].strip()
            if not kampo_nomo:
                continue
            self.db.execute(
                "INSERT INTO shablonaj_kampoj"
                " (uuid, shablono_uuid, kampo_nomo, kampo_tipo,"
                "  estas_deviga, ordo)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (field_uuid, tpl_uuid, kampo_nomo,
                 f.get("tipo", "text"), 1 if is_required else 0, i),
            )
        return self.get_template(tpl_uuid)

    def get_template(self, uuid_: str) -> dict[str, Any] | None:
        """Get a template with its fields."""
        tpl = self.db.execute_one(
            "SELECT * FROM shablonoj WHERE uuid = ?", (uuid_,),
        )
        if not tpl:
            return None
        tpl["fields"] = self.db.execute(
            "SELECT * FROM shablonaj_kampoj WHERE shablono_uuid = ?"
            " ORDER BY ordo", (uuid_,),
        )
        return tpl

    def get_template_by_name(self, name: str) -> dict[str, Any] | None:
        """Get a template by name."""
        tpl = self.db.execute_one(
            "SELECT * FROM shablonoj WHERE nomo = ?", (name,),
        )
        if not tpl:
            return None
        tpl["fields"] = self.db.execute(
            "SELECT * FROM shablonaj_kampoj WHERE shablono_uuid = ?"
            " ORDER BY ordo", (tpl["uuid"],),
        )
        return tpl

    def list_templates(self) -> list[dict[str, Any]]:
        """List all templates (without fields)."""
        return self.db.execute(
            "SELECT * FROM shablonoj ORDER BY nomo",
        )

    def update_template(self, uuid_: str,
                        data: dict[str, Any]) -> dict[str, Any]:
        """Update a template — name, title_placeholder, and fields.

        WARNING: If fields are modified and existing todos have data
        in removed fields, this should be checked before calling
        (see template_fields_in_use).
        """
        now = datetime.now(timezone.utc).isoformat()
        if "nomo" in data:
            self.db.execute(
                "UPDATE shablonoj SET nomo = ?, modifita_je = ?"
                " WHERE uuid = ?",
                (data["nomo"], now, uuid_),
            )
        if "title_placeholder" in data:
            self.db.execute(
                "UPDATE shablonoj SET title_placeholder = ?, modifita_je = ?"
                " WHERE uuid = ?",
                (data["title_placeholder"], now, uuid_),
            )
        if "fields" in data:
            # Replace all fields
            self.db.execute(
                "DELETE FROM shablonaj_kampoj WHERE shablono_uuid = ?",
                (uuid_,),
            )
            for i, f in enumerate(data["fields"]):
                field_uuid = str(uuid.uuid4())
                kampo_nomo = f.get("nomo", "").strip()
                is_required = kampo_nomo.startswith("!")
                if is_required:
                    kampo_nomo = kampo_nomo[1:].strip()
                if not kampo_nomo:
                    continue
                self.db.execute(
                    "INSERT INTO shablonaj_kampoj"
                    " (uuid, shablono_uuid, kampo_nomo, kampo_tipo,"
                    "  estas_deviga, ordo)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (field_uuid, uuid_, kampo_nomo,
                     f.get("tipo", "text"), 1 if is_required else 0, i),
                )
        self.db.execute(
            "UPDATE shablonoj SET modifita_je = ? WHERE uuid = ?",
            (now, uuid_),
        )
        return self.get_template(uuid_)

    def delete_template(self, uuid_: str) -> None:
        """Delete a template."""
        self.db.execute(
            "DELETE FROM shablonoj WHERE uuid = ?", (uuid_,),
        )

    def template_fields_in_use(self, template_uuid: str
                                ) -> dict[str, int]:
        """Check which template fields have values in existing todos.

        Returns a dict of field_name -> count of non-empty values.
        """
        tpl = self.get_template(template_uuid)
        if not tpl:
            return {}
        result: dict[str, int] = {}
        todos = self.db.execute(
            "SELECT uuid FROM taskoj WHERE shablono_uuid = ?",
            (template_uuid,),
        )
        if not todos:
            return {}
        # We store template field values in the description as JSON
        # when using templates. Check for non-empty values.
        for field in tpl.get("fields", []):
            count = 0
            for todo in todos:
                desc = self.db.execute_one(
                    "SELECT priskribo FROM taskoj WHERE uuid = ?",
                    (todo["uuid"],),
                )
                if desc and desc.get("priskribo"):
                    import json
                    try:
                        tpl_data = json.loads(desc["priskribo"])
                        if isinstance(tpl_data, dict):
                            val = tpl_data.get(field["kampo_nomo"], "")
                            if val:
                                count += 1
                    except (json.JSONDecodeError, TypeError):
                        pass
            if count > 0:
                result[field["kampo_nomo"]] = count
        return result
