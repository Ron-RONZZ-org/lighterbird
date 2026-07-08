"""Command handlers for ``!todo list``, ``!todo tree``, and ``!todo search``.

Registered paths:
    - todo.list
    - todo.tree
    - todo.search
"""

from __future__ import annotations

from typing import Any

from lightercore.permissions import PermissionLevel
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_todo_service
from lighterbird.todo.services import TodoService


@command("todo.list", permission_level=PermissionLevel.READ)
def todo_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo list [--status pending|done] [--tags tag1,tag2]
                  [--sort created|priority|due|title] [--mode flat|tree]"""
    svc: TodoService = get_todo_service()
    mode = flags.get("mode", "flat")
    status = flags.get("status")
    tags_raw = flags.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None
    sort = flags.get("sort")

    if mode == "tree":
        flat = svc.flatten_tree()
        return {"type": "todo-list", "title": "Todos", "data": {
            "todos": flat, "tree": True,
        }}

    todos = svc.search("", status=status, tags=tags, sort=sort)
    return {"type": "todo-list", "title": "Todos", "data": {"todos": todos}}


@command("todo.tree", permission_level=PermissionLevel.READ)
def todo_tree(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo tree [--status pending|done] [--mode tree|flat]"""
    svc: TodoService = get_todo_service()
    mode = flags.get("mode", "tree")
    status = flags.get("status")
    sort = flags.get("sort")

    if mode == "flat":
        todos = svc.search("", status=status) if status else svc.list(sort=sort)
        return {"type": "todo-list", "title": "Todos", "data": {"todos": todos}}

    flat = svc.flatten_tree()
    return {"type": "todo-list", "title": "Todos", "data": {
        "todos": flat, "tree": True,
    }}


@command("todo.search", permission_level=PermissionLevel.READ)
def todo_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo search <query> [--status STATE] [--tags tag1,tag2]"""
    svc: TodoService = get_todo_service()
    query = " ".join(remaining) if remaining else flags.get("query", "")
    status = flags.get("status")
    tags_raw = flags.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None
    sort = flags.get("sort")
    todos = svc.search(query, status=status, tags=tags, sort=sort)
    return {
        "type": "todo-list",
        "title": "Todo Search",
        "data": {"todos": todos},
    }
