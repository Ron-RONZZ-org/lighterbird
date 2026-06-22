"""Command handlers for the ``!todo`` domain.

Registered paths:
    - todo.list
    - todo.add
    - todo.view
    - todo.done
    - todo.modify
    - todo.remove
    - todo.search
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_todo_service
from lighterbird.todo.services import TodoService


@command("todo.list")
def todo_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo list [--status pending|done]"""
    svc: TodoService = get_todo_service()
    status = flags.get("status")
    todos = svc.search("", status=status) if status else svc.list()
    return {"type": "status", "title": "Todos", "data": {"todos": todos}}


@command("todo.add")
def todo_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo add <title> [--due DATE] [--priority N] [--description TEXT]"""
    if not remaining:
        raise CommandValidationError("Missing todo title.", "Usage: !todo add <title> [--due DATE] [--priority N]")
    title = " ".join(remaining)
    data = {
        "titolo": title,
        "priskribo": flags.get("description", ""),
        "prioritato": int(flags.get("priority", 5)),
        "limdato": flags.get("due", ""),
    }
    svc: TodoService = get_todo_service()
    todo = svc.create(data)
    return {"type": "status", "title": "Todo Added", "data": {"uuid": todo["uuid"], "title": title}}


@command("todo.view")
def todo_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo view <uuid>"""
    if not remaining:
        raise CommandValidationError("Missing todo UUID.", "Usage: !todo view <uuid>")
    svc: TodoService = get_todo_service()
    todo = svc.get(remaining[0])
    if not todo:
        raise CommandValidationError(f"Todo not found: {remaining[0][:8]}")
    return {"type": "status", "title": todo.get("titolo", "(untitled)"), "data": todo}


@command("todo.done")
def todo_done(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo done <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError("Missing todo UUID.", "Usage: !todo done <uuid>")
    svc: TodoService = get_todo_service()
    done = []
    for uuid in remaining:
        try:
            svc.mark_done(uuid)
            done.append(uuid[:8])
        except Exception:
            pass
    return {"type": "status", "title": "Todo(s) Done", "data": {"done": done}}


@command("todo.modify")
def todo_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo modify <uuid> [--title TITLE] [--description DESC] [--priority N] [--due DATE] [--status STATE]"""
    if not remaining:
        raise CommandValidationError("Missing todo UUID.", "Usage: !todo modify <uuid> [--title ...]")
    uuid = remaining[0]
    svc: TodoService = get_todo_service()
    updates = {}
    field_map = {"title": "titolo", "description": "priskribo", "due": "limdato", "status": "stato"}
    for flag_key, db_key in field_map.items():
        if flag_key in flags:
            updates[db_key] = flags[flag_key]
    if "priority" in flags:
        updates["prioritato"] = int(flags["priority"])
    if not updates:
        raise CommandValidationError("No fields to modify.", "Usage: !todo modify <uuid> [--title ...]")
    svc.update(uuid, updates)
    return {"type": "status", "title": "Todo Modified", "data": {"uuid": uuid[:8]}}


@command("todo.remove")
def todo_remove(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo remove <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError("Missing todo UUID(s).", "Usage: !todo remove <uuid> [uuid...]")
    svc: TodoService = get_todo_service()
    removed = []
    for uuid in remaining:
        try:
            svc.delete(uuid)
            removed.append(uuid[:8])
        except Exception:
            pass
    return {"type": "status", "title": "Todo(s) Removed", "data": {"removed": removed}}


@command("todo.search")
def todo_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo search <query> [--status STATE]"""
    svc: TodoService = get_todo_service()
    query = " ".join(remaining) if remaining else flags.get("query", "")
    status = flags.get("status")
    todos = svc.search(query, status=status)
    return {"type": "status", "title": "Todo Search", "data": {"todos": todos}}
