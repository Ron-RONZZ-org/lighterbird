"""Command handlers for ``!todo`` CRUD operations.

Registered paths:
    - todo.add
    - todo.view
    - todo.done
    - todo.modify
    - todo.delete
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlparse

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_todo_service
from lighterbird.todo.services import TodoService


@command("todo.add")
def todo_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo add <title> [--parent UUID] [--dependency UUID]
                      [--file PATH|URL] [--template NAME]
                      [--due DATE] [--priority N] [--description TEXT]
                      [--text name:value ...]"""
    if not remaining:
        raise CommandValidationError(
            "Missing todo title.",
            "Usage: !todo add <title> [--parent UUID] [--template NAME]",
        )
    title = " ".join(remaining)
    svc: TodoService = get_todo_service()

    template_data = None
    if "template" in flags:
        tpl = svc.get_template_by_name(flags["template"])
        if not tpl:
            raise CommandValidationError(
                f"Template not found: {flags['template']}",
                "Use !todo template list to see available templates.",
            )
        template_data = tpl
        if tpl.get("title_placeholder") and not remaining:
            title = tpl["title_placeholder"]

    data: dict[str, Any] = {
        "title": title,
        "description": flags.get("description", ""),
        "priority": flags.get("priority", "5"),
        "due_date": flags.get("due"),
    }

    # Parent (first comma-separated value)
    if "parent" in flags:
        parent_uuids = [u.strip() for u in flags["parent"].split(",") if u.strip()]
        if parent_uuids:
            parent = svc.get(parent_uuids[0])
            if not parent:
                raise CommandValidationError(
                    f"Parent todo not found: {parent_uuids[0][:8]}",
                )
            data["parent_uuid"] = parent["uuid"]

    # Template reference
    if template_data:
        data["template_uuid"] = template_data["uuid"]

    # Template field values (stored as JSON in description)
    text_fields = [v for k, v in flags.items() if k.startswith("text_")]
    if text_fields:
        tpl_values: dict[str, str] = {}
        try:
            existing = json.loads(data.get("description") or "{}")
            if isinstance(existing, dict):
                tpl_values.update(existing)
        except (json.JSONDecodeError, TypeError):
            pass
        for tf in text_fields:
            if ":" in tf:
                key, val = tf.split(":", 1)
                tpl_values[key.strip()] = val.strip()
            else:
                tpl_values[tf] = ""
        data["description"] = json.dumps(tpl_values)

    # Dependency (comma-separated list)
    depends_on_raw = flags.get("dependency")
    if depends_on_raw:
        dep_uuids = [u.strip() for u in depends_on_raw.split(",") if u.strip()]
        resolved = []
        for du in dep_uuids:
            dep_todo = svc.get(du)
            if not dep_todo:
                raise CommandValidationError(
                    f"Dependency todo not found: {du[:8]}",
                )
            resolved.append(dep_todo["uuid"])
        data["_depends_on"] = resolved

    # ── Tags ──────────────────────────────────────────────────────────
    tags_raw = flags.get("tags", "")
    if tags_raw:
        tag_names = [t.strip() for t in tags_raw.split(",") if t.strip()]
        for tag_name in tag_names:
            try:
                svc.create_label({"name": tag_name})
            except ValueError:
                pass  # label already exists
        data["_tags"] = tag_names

    # ── LLM co-writing ─────────────────────────────────────────────────
    cowrite_instr = flags.get("cowrite", "")
    if cowrite_instr:
        import asyncio
        from lighterbird.server.cowrite.engine import cowrite as _cowrite_call

        fields = {"title": data["title"], "description": data.get("description", "")}
        try:
            result = asyncio.run(_cowrite_call(
                form_type="todo-add",
                fields=fields,
                instruction=cowrite_instr,
            ))
            data["title"] = result["revised"].get("title", data["title"])
            if "description" in result["revised"]:
                data["description"] = result["revised"]["description"]
        except (RuntimeError, ValueError) as exc:
            raise CommandValidationError(f"Co-writing failed: {exc}")

    todo = svc.create(data)

    # File attachment (comma-separated list)
    if "file" in flags:
        file_paths = [f.strip() for f in flags["file"].split(",") if f.strip()]
        for fp in file_paths:
            try:
                _attach_file(svc, todo["uuid"], fp)
            except CommandValidationError:
                pass

    return {
        "type": "status",
        "title": "Todo Added",
        "data": {"uuid": todo["uuid"], "title": title},
    }


def _attach_file(svc: TodoService, todo_uuid: str, path_or_url: str) -> None:
    """Attach a file (local path or URL) to a todo."""
    import hashlib

    parsed = urlparse(path_or_url)
    is_url = parsed.scheme in ("http", "https", "ftp")

    if is_url:
        orig_name = os.path.basename(parsed.path) or "remote_file"
        svc.add_attachment(
            todo_uuid,
            original_name=orig_name,
            original_path=path_or_url,
        )
    elif os.path.exists(path_or_url):
        orig_name = os.path.basename(path_or_url)
        size = os.path.getsize(path_or_url)
        md5 = hashlib.md5()
        with open(path_or_url, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk)
        svc.add_attachment(
            todo_uuid,
            original_name=orig_name,
            original_path=path_or_url,
            size=size,
            md5_checksum=md5.hexdigest(),
        )
    else:
        raise CommandValidationError(
            f"File not found: {path_or_url}",
            "Provide a valid local path or URL.",
        )


@command("todo.view")
def todo_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo view <uuid>"""
    if not remaining:
        raise CommandValidationError(
            "Missing todo UUID.", "Usage: !todo view <uuid>",
        )
    svc: TodoService = get_todo_service()
    todo = svc.get_with_children(remaining[0])
    if not todo:
        raise CommandValidationError(
            f"Todo not found: {remaining[0][:8]}",
        )
    todo["dependencies"] = svc.get_dependencies(todo["uuid"])
    todo["blocked_tasks"] = svc.get_blocked_tasks(todo["uuid"])
    todo["attachments"] = svc.get_attachments(todo["uuid"])
    return {
        "type": "status",
        "title": todo.get("title", "(untitled)"),
        "data": todo,
    }


@command("todo.done")
def todo_done(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo done <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError(
            "Missing todo UUID.", "Usage: !todo done <uuid>",
        )
    svc: TodoService = get_todo_service()
    done = []
    for uuid_ in remaining:
        try:
            svc.mark_done(uuid_)
            done.append(uuid_[:8])
        except Exception:
            pass
    return {"type": "status", "title": "Todo(s) Done", "data": {"done": done}}


@command("todo.modify")
def todo_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo modify <uuid> [--title TITLE] [--description DESC]
                           [--priority N] [--due DATE] [--status STATE]
                           [--parent UUID]"""
    if not remaining:
        raise CommandValidationError(
            "Missing todo UUID.", "Usage: !todo modify <uuid> [--title ...]",
        )
    uuid_ = remaining[0]
    svc: TodoService = get_todo_service()
    updates: dict[str, Any] = {}
    field_map = {
        "title": "title",
        "description": "description",
        "due": "due_date",
        "status": "status",
    }
    for flag_key, db_key in field_map.items():
        if flag_key in flags:
            updates[db_key] = flags[flag_key]
    if "priority" in flags:
        updates["priority"] = flags["priority"]
    if "parent" in flags:
        parent_val = flags["parent"]
        if parent_val.lower() == "none" or parent_val == "":
            updates["parent_uuid"] = None
        else:
            parent = svc.get(parent_val)
            if not parent:
                raise CommandValidationError(
                    f"Parent todo not found: {parent_val[:8]}",
                )
            updates["parent_uuid"] = parent["uuid"]

    # ── Tags ──────────────────────────────────────────────────────────
    if "tags" in flags:
        tags_raw = flags["tags"]
        if tags_raw.strip():
            tag_names = [t.strip() for t in tags_raw.split(",") if t.strip()]
            # Ensure labels exist
            for tag_name in tag_names:
                try:
                    svc.create_label({"name": tag_name})
                except ValueError:
                    pass
            updates["_tags"] = tag_names
        else:
            updates["_tags"] = []  # empty = clear all tags

    if not updates:
        raise CommandValidationError(
            "No fields to modify.",
            "Usage: !todo modify <uuid> [--title ...]",
        )
    svc.update(uuid_, updates)
    return {
        "type": "status",
        "title": "Todo Modified",
        "data": {"uuid": uuid_[:8]},
    }


@command("todo.delete")
def todo_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo delete <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError(
            "Missing todo UUID(s).", "Usage: !todo delete <uuid> [uuid...]",
        )
    svc: TodoService = get_todo_service()
    removed = []
    for uuid_ in remaining:
        try:
            svc.delete(uuid_)
            removed.append(uuid_[:8])
        except Exception:
            pass
    return {
        "type": "status",
        "title": "Todo(s) Deleted",
        "data": {"removed": removed},
    }
