"""Template mixin for todos: template CRUD and field analytics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any


class _TodoTemplateMixin:
    """Mixin providing template creation, retrieval, update, deletion,
    and field-usage analytics for the TodoService class."""

    # ── Templates ───────────────────────────────────────────────────────

    def create_template(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
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
        now = datetime.now(UTC).isoformat()
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
