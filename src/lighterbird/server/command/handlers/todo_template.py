"""Command handlers for ``!todo template`` operations.

Registered paths:
    - todo.template
    - todo.template.list
    - todo.template.add
    - todo.template.view
    - todo.template.modify
    - todo.template.delete
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_todo_service
from lighterbird.todo.services import TodoService


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
                "  !todo template delete <name>   — Delete a template\n"
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
        "type": "templates",
        "title": "Templates",
        "data": {"templates": templates},
    }


@command("todo.template.add", interactive=True)
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


@command("todo.template.modify", interactive=True)
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


@command("todo.template.delete", interactive=True)
def todo_template_delete(remaining: list[str],
                         flags: dict[str, str]) -> dict[str, Any]:
    """!todo template delete <name>"""
    if not remaining:
        raise CommandValidationError(
            "Missing template name.",
            "Usage: !todo template delete <name>",
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
        "title": "Template Deleted",
        "data": {"name": tpl["name"]},
    }
