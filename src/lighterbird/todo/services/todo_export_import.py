"""Markdown export/import mixin for todos."""

from __future__ import annotations

from typing import Any


def _render_child_tree(children: list[dict[str, Any]],
                       depth: int = 0) -> list[str]:
    """Render a list of child todos as indented markdown bullet list."""
    lines: list[str] = []
    for child in children:
        prefix = "  " * depth + "- "
        title = child.get("title", "")
        uuid_ = child.get("uuid", "")
        lines.append(f"{prefix}{title} (`{uuid_[:8]}`)")
        grandkids = child.get("children", [])
        if grandkids:
            lines.extend(_render_child_tree(grandkids, depth + 1))
    return lines


class _TodoExportImportMixin:
    """Mixin providing Markdown export and import for the TodoService class."""

    # ── Markdown Export / Import ──────────────────────────────────────────

    def export_md(self, uuid: str | None = None,
                  uuids: list[str] | None = None) -> str:
        """Export one or more todos as Markdown with YAML frontmatter.

        Args:
            uuid: Single todo UUID to export (with tree hierarchy).
            uuids: List of todo UUIDs to export.
                If neither *uuid* nor *uuids* is given, all todos are exported.

        Returns:
            Full .md string with YAML frontmatter for each todo,
            concatenated with ``\\n\\n`` between entries.
        """
        from lighterbird.core.yaml_frontmatter import wrap

        todos: list[dict[str, Any]] = []
        if uuid:
            todo = self.get_with_children(uuid)
            if todo:
                todos.append(todo)
        elif uuids:
            for uid in uuids:
                todo = self.get_with_children(uid)
                if todo:
                    todos.append(todo)
        else:
            all_todos = self.list(limit=10000)
            for t in all_todos:
                todo = self.get_with_children(t["uuid"])
                if todo:
                    todos.append(todo)

        parts: list[str] = []
        for todo in todos:
            meta: dict[str, Any] = {
                "uuid": todo["uuid"],
                "domain": "todo",
                "created_at": todo.get("created_at"),
                "updated_at": todo.get("updated_at"),
                "status": todo.get("status"),
                "priority": todo.get("priority"),
                "due": todo.get("due_date"),
                "parent_uuid": todo.get("parent_uuid"),
            }
            labels = todo.get("labels", [])
            if labels:
                meta["tags"] = [l["name"] for l in labels]

            deps = self.get_dependencies(todo["uuid"])
            if deps:
                meta["dependencies"] = [d["uuid"] for d in deps]

            body_parts: list[str] = []
            title = todo.get("title", "")
            if title:
                body_parts.append(f"## {title}")
            description = todo.get("description", "")
            if description:
                body_parts.append("")
                body_parts.append(description)
            children = todo.get("children", [])
            if children:
                body_parts.append("")
                body_parts.append("### Children")
                for line in _render_child_tree(children):
                    body_parts.append(line)
            if deps:
                body_parts.append("")
                body_parts.append("### Dependencies")
                for d in deps:
                    body_parts.append(
                        f"- {d.get('title', '')} (`{d['uuid'][:8]}`)",
                    )

            body = "\n".join(body_parts).strip()
            parts.append(wrap(body, meta))

        return "\n\n".join(parts)

    def import_md(self, path: str) -> list[str]:
        """Import todos from a .md file with YAML frontmatter.

        The file may contain one or more entries, each delimited by
        YAML frontmatter (``---\\n...\\n---\\n``).

        Args:
            path: Path to the .md file.

        Returns:
            List of created todo UUIDs.
        """
        import re

        import yaml

        with open(path, "r") as f:
            text = f.read()

        entries: list[tuple[dict[str, Any], str]] = []
        pattern = r"(?s)(?:^|\n)---\n(.*?)\n---\n(.*?)(?=\n---\n|\Z)"
        for m in re.finditer(pattern, "\n" + text):
            yaml_raw = m.group(1)
            body = m.group(2).strip()
            try:
                meta = yaml.safe_load(yaml_raw) or {}
                if not isinstance(meta, dict):
                    meta = {}
            except yaml.YAMLError:
                meta = {}
            entries.append((meta, body))

        if not entries:
            from lighterbird.core.yaml_frontmatter import unwrap

            meta, body = unwrap(text)
            if meta:
                entries.append((meta, body))

        created: list[str] = []
        for meta, body in entries:
            title = meta.get("title", "")
            if not title:
                h2_match = re.search(r"^##\s+(.+)$", body, re.MULTILINE)
                if h2_match:
                    title = h2_match.group(1).strip()
                else:
                    title = "(imported)"

            description = ""
            if title:
                desc_text = re.sub(
                    r"^##\s+.*$", "", body, count=1, flags=re.MULTILINE,
                ).strip()
                desc_text = re.sub(
                    r"(?s)^### +Children\b.*?(?=\n###|\n\Z|\Z)",
                    "", desc_text,
                ).strip()
                desc_text = re.sub(
                    r"(?s)^### +Dependencies\b.*?(?=\n###|\n\Z|\Z)",
                    "", desc_text,
                ).strip()
                description = desc_text.strip()

            data: dict[str, Any] = {
                "title": title,
                "description": description,
                "priority": str(meta.get("priority", "5")),
                "status": meta.get("status", "pending"),
                "due_date": meta.get("due"),
                "parent_uuid": meta.get("parent_uuid"),
            }

            tags = meta.get("tags", [])
            if tags:
                for tag_name in tags:
                    existing = self.db.execute_one(
                        "SELECT name FROM labels WHERE name = ?", (tag_name,),
                    )
                    if not existing:
                        try:
                            self.create_label({"name": tag_name})
                        except ValueError:
                            pass
                data["_tags"] = tags

            deps = meta.get("dependencies", [])
            if deps:
                data["_depends_on"] = deps

            result = self.create(data)
            created.append(result["uuid"])

        return created
