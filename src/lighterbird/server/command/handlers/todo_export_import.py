"""Command handlers for ``!todo export`` and ``!todo import``.

Registered paths:
    - todo.export
    - todo.export.md
    - todo.import
    - todo.import.md
"""

from __future__ import annotations

import datetime
from typing import Any

from lighterbird.core.paths import safe_resolve_path
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_todo_service
from lighterbird.todo.services import TodoService


@command("todo.export")
def todo_export_root(remaining: list[str],
                     flags: dict[str, str]) -> dict[str, Any]:
    """!todo export — Show available export subcommands."""
    return {
        "type": "status",
        "title": "Export Commands",
        "data": {
            "_summary": (
                "Available !todo export commands:\n"
                "  !todo export md <uuid>         — Export a single todo\n"
                "  !todo export md --all          — Export all todos\n"
            ),
        },
    }


@command("todo.export.md")
def todo_export_md(remaining: list[str],
                   flags: dict[str, str]) -> dict[str, Any]:
    """!todo export md <uuid> | !todo export md --all"""
    svc: TodoService = get_todo_service()

    if "all" in flags:
        result = svc.export_md()
    elif remaining:
        result = svc.export_md(uuid=remaining[0])
    else:
        raise CommandValidationError(
            "Missing todo UUID or --all flag.",
            "Usage: !todo export md <uuid> | !todo export md --all",
        )

    if not result:
        raise CommandValidationError(
            f"Todo not found: {remaining[0][:8]}" if remaining
            else "No todos to export.",
        )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"todo_export_{timestamp}.md"
    with open(filename, "w") as f:
        f.write(result)

    return {
        "type": "status",
        "title": "Todo Exported",
        "data": {"file": filename, "size": len(result)},
    }


@command("todo.import")
def todo_import_root(remaining: list[str],
                     flags: dict[str, str]) -> dict[str, Any]:
    """!todo import — Show available import subcommands."""
    return {
        "type": "status",
        "title": "Import Commands",
        "data": {
            "_summary": (
                "Available !todo import commands:\n"
                "  !todo import md <path>         — Import from .md file\n"
            ),
        },
    }


@command("todo.import.md")
def todo_import_md(remaining: list[str],
                   flags: dict[str, str]) -> dict[str, Any]:
    """!todo import md <path>"""
    if not remaining:
        raise CommandValidationError(
            "Missing file path.",
            "Usage: !todo import md <path>",
        )

    try:
        safe_resolve_path(remaining[0])
    except (ValueError, FileNotFoundError, IsADirectoryError) as e:
        raise CommandValidationError(str(e))

    path = remaining[0]
    svc: TodoService = get_todo_service()

    try:
        created = svc.import_md(path)
    except FileNotFoundError as e:
        raise CommandValidationError(str(e)) from e

    return {
        "type": "status",
        "title": "Todo(s) Imported",
        "data": {"created": created, "count": len(created)},
    }
