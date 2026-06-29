"""Command handlers for the ``!todo`` domain.

Registered paths:
    - todo.list / todo.tree
    - todo.add
    - todo.view
    - todo.done
    - todo.modify
    - todo.remove
    - todo.search
    - todo.template.*
"""

from __future__ import annotations

import json
from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_todo_service
from lighterbird.todo.services import TodoService


@command("todo")
def todo_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo — Show available todo subcommands."""
    return {
        "type": "status",
        "title": "Todo Commands",
        "data": {
            "_summary": (
                "Available !todo commands:\n"
                "  !todo list                — List todos (flat)\n"
                "  !todo tree                — List todos (tree view)\n"
                "  !todo add <title>         — Add a todo\n"
                "  !todo view <uuid>         — View a todo\n"
                "  !todo done <uuid> [...]   — Mark todo(s) as done\n"
                "  !todo modify <uuid>       — Modify a todo\n"
                "  !todo remove <uuid> [...] — Remove a todo(s)\n"
                "  !todo search <query>      — Search todos\n"
                "  !todo draft               — List / recall todo drafts\n"
                "  !todo template            — Manage templates\n"
                "\nFlags for !todo add:\n"
                "  --parent <uuid>           — Set parent (subtask)\n"
                "  --dependency <uuid>       — Set dependency\n"
                "  --template <name>         — Use a template\n"
                "  --file <path|url>         — Attach a file\n"
                "  --due <DATE>, --priority N, --description TEXT\n"
                "  --text <name>:<value>     — Template field value\n"
            ),
        },
    }


@command("todo.list")
def todo_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo list [--status pending|done]"""
    svc: TodoService = get_todo_service()
    status = flags.get("status")
    todos = svc.search("", status=status) if status else svc.list()
    return {"type": "todo-list", "title": "Todos", "data": {"todos": todos}}


@command("todo.tree")
def todo_tree(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo tree [--status pending|done]"""
    svc: TodoService = get_todo_service()
    flat = svc.flatten_tree()
    return {"type": "todo-list", "title": "Todos (Tree)", "data": {
        "todos": flat, "tree": True,
    }}


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
    import os
    from urllib.parse import urlparse

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
        import hashlib
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


@command("todo.remove")
def todo_remove(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo remove <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError(
            "Missing todo UUID(s).", "Usage: !todo remove <uuid> [uuid...]",
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
        "title": "Todo(s) Removed",
        "data": {"removed": removed},
    }


@command("todo.search")
def todo_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo search <query> [--status STATE]"""
    svc: TodoService = get_todo_service()
    query = " ".join(remaining) if remaining else flags.get("query", "")
    status = flags.get("status")
    todos = svc.search(query, status=status)
    return {
        "type": "todo-list",
        "title": "Todo Search",
        "data": {"todos": todos},
    }


# ═══════════════════════════════════════════════════════════════════════
# Template subcommands
# ═══════════════════════════════════════════════════════════════════════


@command("todo.template")
def todo_template_root(remaining: list[str],
                       flags: dict[str, str]) -> dict[str, Any]:
    """!todo template — Show available template subcommands."""
    return {
        "type": "status",
        "title": "Template Commands",
        "data": {
            "_summary": (
                "Available !todo template commands:\n"
                "  !todo template list            — List templates\n"
                "  !todo template add <name>      — Create a template\n"
                "  !todo template view <name>     — View a template\n"
                "  !todo template modify <name>   — Modify a template\n"
                "  !todo template remove <name>   — Remove a template\n"
                "\nFlags for !todo template add:\n"
                "  --text <name>       Add a text field (repeatable)\n"
                "  --file <name>       Add a file field (repeatable)\n"
                "  --markdown <name>   Add a markdown field (repeatable)\n"
                "  --title-placeholder <text>  Default title text\n"
                "  Prefix name with ! for required fields "
                "(e.g. --text !deadline)\n"
            ),
        },
    }


@command("todo.template.list")
def todo_template_list(remaining: list[str],
                       flags: dict[str, str]) -> dict[str, Any]:
    """!todo template list"""
    svc: TodoService = get_todo_service()
    templates = svc.list_templates()
    return {
        "type": "status",
        "title": "Templates",
        "data": {"templates": templates},
    }


@command("todo.template.add")
def todo_template_add(remaining: list[str],
                      flags: dict[str, str]) -> dict[str, Any]:
    """!todo template add <name> [--text NAME] [--file NAME]
                                  [--markdown NAME] [--title-placeholder TEXT]"""
    if not remaining:
        raise CommandValidationError(
            "Missing template name.",
            "Usage: !todo template add <name> [--text field] ...",
        )
    name = " ".join(remaining)
    svc: TodoService = get_todo_service()

    fields = []
    for flag_key in ("text", "file", "markdown"):
        if flag_key in flags:
            raw = flags[flag_key]
            names = [n.strip() for n in raw.replace(",", " ").split()
                     if n.strip()]
            for n in names:
                fields.append({"name": n, "type": flag_key})

    data = {
        "name": name,
        "title_placeholder": flags.get("title-placeholder", ""),
        "fields": fields,
    }
    try:
        tpl = svc.create_template(data)
    except ValueError as e:
        raise CommandValidationError(str(e)) from e

    return {
        "type": "status",
        "title": "Template Created",
        "data": {"uuid": tpl["uuid"], "name": tpl["name"]},
    }


@command("todo.template.view")
def todo_template_view(remaining: list[str],
                       flags: dict[str, str]) -> dict[str, Any]:
    """!todo template view <name>"""
    if not remaining:
        raise CommandValidationError(
            "Missing template name.",
            "Usage: !todo template view <name>",
        )
    svc: TodoService = get_todo_service()
    tpl = svc.get_template_by_name(" ".join(remaining))
    if not tpl:
        raise CommandValidationError(
            f"Template not found: {' '.join(remaining)}",
        )
    return {"type": "status", "title": f"Template: {tpl['name']}", "data": tpl}


@command("todo.template.modify")
def todo_template_modify(remaining: list[str],
                         flags: dict[str, str]) -> dict[str, Any]:
    """!todo template modify <name> [--title-placeholder TEXT]
                                     [--new-name NAME]
                                     [--text NAME] [--file NAME]
                                     [--markdown NAME]"""
    if not remaining:
        raise CommandValidationError(
            "Missing template name.",
            "Usage: !todo template modify <name> [--new-name NAME] ...",
        )
    svc: TodoService = get_todo_service()
    tpl = svc.get_template_by_name(" ".join(remaining))
    if not tpl:
        raise CommandValidationError(
            f"Template not found: {' '.join(remaining)}",
        )

    data: dict[str, Any] = {}
    if "new-name" in flags:
        data["name"] = flags["new-name"]
    if "title-placeholder" in flags:
        data["title_placeholder"] = flags["title-placeholder"]

    fields = []
    for flag_key in ("text", "file", "markdown"):
        if flag_key in flags:
            names = [n.strip()
                     for n in flags[flag_key].replace(",", " ").split()
                     if n.strip()]
            for n in names:
                fields.append({"name": n, "type": flag_key})
    if fields:
        in_use = svc.template_fields_in_use(tpl["uuid"])
        removed_non_empty = {
            fn for fn in in_use
            if not any(f["name"].lstrip("!") == fn for f in fields)
        }
        if removed_non_empty:
            detail = ", ".join(
                f"'{fn}' ({cnt} todos)" for fn, cnt in in_use.items()
                if fn in removed_non_empty
            )
            return {
                "type": "confirm",
                "title": "Data Loss Warning",
                "message": (
                    f"The following fields have non-empty values "
                    f"in existing todos and will be removed:\n"
                    f"  {detail}\n\n"
                    f"Remove from template anyway?",
                ),
                "data": {
                    "confirm_command":
                        f"todo template modify {' '.join(remaining)}",
                    "fields": fields,
                    "update_data": data,
                },
            }
        data["fields"] = fields

    if not data:
        raise CommandValidationError(
            "No fields to modify.",
            "Usage: !todo template modify <name> [--new-name NAME] ...",
        )

    updated = svc.update_template(tpl["uuid"], data)
    return {
        "type": "status",
        "title": "Template Modified",
        "data": {"uuid": updated["uuid"], "name": updated["name"]},
    }


@command("todo.template.remove")
def todo_template_remove(remaining: list[str],
                         flags: dict[str, str]) -> dict[str, Any]:
    """!todo template remove <name>"""
    if not remaining:
        raise CommandValidationError(
            "Missing template name.",
            "Usage: !todo template remove <name>",
        )
    svc: TodoService = get_todo_service()
    tpl = svc.get_template_by_name(" ".join(remaining))
    if not tpl:
        raise CommandValidationError(
            f"Template not found: {' '.join(remaining)}",
        )
    svc.delete_template(tpl["uuid"])
    return {
        "type": "status",
        "title": "Template Removed",
        "data": {"name": tpl["name"]},
    }
