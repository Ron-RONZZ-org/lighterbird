"""LLM tools for the todo domain.

Tools:
    - ``todo.find`` -- Search tasks by title, status, priority, due date, or tags
    - ``todo.read`` -- Full task details with subtasks and dependencies
    - ``todo.create`` -- Add a new task
    - ``todo.update`` -- Modify task fields
    - ``todo.done`` -- Mark a task as complete
    - ``todo.delete`` -- Delete a task
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lightercore.permissions import PermissionLevel

from lighterbird.server.deps import get_todo_service
from lighterbird.server.llm.tools import llm_tool


def _parse_iso(value: str | None) -> str | None:
    """Normalize an ISO date string."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return value


def _todo_preview(t: dict) -> dict:
    """Return a preview of a todo dict."""
    return {
        "uuid": t.get("uuid", ""),
        "title": t.get("title", ""),
        "status": t.get("status", ""),
        "priority": t.get("priority", 0),
        "due": t.get("due", ""),
        "created_at": t.get("created_at", ""),
        "tags": t.get("_tags", []),
    }


# ── Find tasks ────────────────────────────────────────────────────────────────


@llm_tool(
    name="todo.find",
    description="Search tasks by title, status, priority, due date, or tags. Supports filtering by completion status.",
    params=[
        {"name": "query", "type": "string", "description": "Search term in title"},
        {"name": "status", "type": "string", "description": "Filter by status (e.g. 'pending', 'completed', 'cancelled')"},
        {"name": "priority_min", "type": "number", "description": "Minimum priority value (higher = more urgent)"},
        {"name": "due_before", "type": "string", "description": "ISO date — tasks due before this date"},
        {"name": "due_after", "type": "string", "description": "ISO date — tasks due after this date"},
        {"name": "tag", "type": "string", "description": "Filter by tag name"},
        {"name": "is_done", "type": "boolean", "description": "Filter by completion status"},
        {"name": "max_results", "type": "number", "description": "Maximum results (default 30)"},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_todo_find(**kwargs: Any) -> dict:
    """Search tasks with filters."""
    query = kwargs.get("query", "")
    status = kwargs.get("status", "")
    tag = kwargs.get("tag", "")
    limit = int(kwargs.get("max_results", 30))

    service = get_todo_service()
    try:
        results = service.search(
            field="title",
            query=query or "",
            limit=limit * 2,  # fetch extra for post-filtering
        )

        # Post-filter in Python for complex filters
        filtered = []
        for t in results:
            if status and (t.get("status") or "").lower() != status.lower():
                continue
            if tag and tag not in (t.get("_tags") or []):
                continue
            if kwargs.get("is_done") is not None:
                is_done = t.get("status") == "completed"
                if bool(kwargs["is_done"]) != is_done:
                    continue
            if kwargs.get("priority_min") is not None:
                try:
                    if (t.get("priority") or 0) < int(kwargs["priority_min"]):
                        continue
                except (ValueError, TypeError):
                    pass
            if kwargs.get("due_before"):
                try:
                    if (t.get("due") or "9999") > kwargs["due_before"]:
                        continue
                except (ValueError, TypeError):
                    pass
            if kwargs.get("due_after"):
                try:
                    if (t.get("due") or "") < kwargs["due_after"]:
                        continue
                except (ValueError, TypeError):
                    pass
            filtered.append(_todo_preview(t))
            if len(filtered) >= limit:
                break

        return {"success": True, "data": filtered, "total": len(filtered)}
    except Exception as exc:
        return {"success": False, "error": f"Todo search failed: {exc}"}


# ── Read task ─────────────────────────────────────────────────────────────────


@llm_tool(
    name="todo.read",
    description="Get full task details by UUID, including subtasks, dependencies, and attachments.",
    params=[
        {"name": "uuid", "type": "string", "description": "Task UUID", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_todo_read(uuid: str = "") -> dict:
    """Get full task details."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_todo_service()
    try:
        task = service.get(uuid)
        if not task:
            return {"success": False, "error": f"Task not found: {uuid}"}

        task_dict = dict(task)
        task_dict["_tags"] = service.get_labels(uuid) or []
        task_dict["_dependencies"] = service.get_dependencies(uuid) or []
        return {"success": True, "data": task_dict}
    except Exception as exc:
        return {"success": False, "error": f"Failed to read task: {exc}"}


# ── Create task ───────────────────────────────────────────────────────────────


@llm_tool(
    name="todo.create",
    description="Add a new task with title, optional description, due date, priority, and tags.",
    params=[
        {"name": "title", "type": "string", "description": "Task title", "required": True},
        {"name": "description", "type": "string", "description": "Task description or notes"},
        {"name": "due", "type": "string", "description": "Due date (ISO format, e.g. '2026-08-01')"},
        {"name": "priority", "type": "number", "description": "Priority value (higher = more urgent)"},
        {"name": "tags", "type": "string", "description": "Comma-separated tags"},
        {"name": "parent_uuid", "type": "string", "description": "UUID of parent task for subtasks"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_todo_create(**kwargs: Any) -> dict:
    """Create a new task."""
    title = kwargs.get("title", "")
    if not title:
        return {"success": False, "error": "title is required"}

    data: dict[str, Any] = {
        "title": title,
        "description": kwargs.get("description", ""),
    }
    if kwargs.get("due"):
        data["due"] = _parse_iso(kwargs["due"]) or kwargs["due"]
    if kwargs.get("priority") is not None:
        data["priority"] = int(kwargs["priority"])
    if kwargs.get("parent_uuid"):
        data["parent_uuid"] = kwargs["parent_uuid"]

    tags_str = kwargs.get("tags", "")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

    service = get_todo_service()
    try:
        result = service.create(data)
        if tags:
            service.add_label(result["uuid"], tags)
        return {"success": True, "data": {"uuid": result.get("uuid", ""), "title": title}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to create task: {exc}"}


# ── Update task ───────────────────────────────────────────────────────────────


@llm_tool(
    name="todo.update",
    description="Modify an existing task's fields. Only provided fields are updated.",
    params=[
        {"name": "uuid", "type": "string", "description": "Task UUID to modify", "required": True},
        {"name": "title", "type": "string", "description": "New title"},
        {"name": "description", "type": "string", "description": "New description"},
        {"name": "due", "type": "string", "description": "New due date (ISO format)"},
        {"name": "priority", "type": "number", "description": "New priority value"},
        {"name": "status", "type": "string", "description": "New status (e.g. 'pending', 'cancelled')"},
        {"name": "tags", "type": "string", "description": "Comma-separated tags (replaces all tags)"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_todo_update(**kwargs: Any) -> dict:
    """Modify a task."""
    uuid = kwargs.get("uuid", "")
    if not uuid:
        return {"success": False, "error": "uuid is required"}

    data: dict[str, Any] = {}
    for field in ("title", "description", "status"):
        if kwargs.get(field) is not None:
            data[field] = kwargs[field]
    if kwargs.get("due") is not None:
        data["due"] = _parse_iso(kwargs["due"]) or kwargs["due"]
    if kwargs.get("priority") is not None:
        data["priority"] = int(kwargs["priority"])
    if kwargs.get("tags") is not None:
        data["_tags"] = [t.strip() for t in kwargs["tags"].split(",") if t.strip()]

    if not data:
        return {"success": False, "error": "No fields to update"}

    service = get_todo_service()
    try:
        result = service.update(uuid, data)
        if not result:
            return {"success": False, "error": f"Task not found: {uuid}"}
        return {"success": True, "data": {"uuid": uuid, "updated": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to update task: {exc}"}


# ── Mark done ─────────────────────────────────────────────────────────────────


@llm_tool(
    name="todo.done",
    description="Mark a task as completed. The task will be set to status 'completed'.",
    params=[
        {"name": "uuid", "type": "string", "description": "Task UUID to mark complete", "required": True},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_todo_done(uuid: str = "") -> dict:
    """Mark a task as completed."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_todo_service()
    try:
        result = service.mark_done(uuid)
        if not result:
            return {"success": False, "error": f"Task not found: {uuid}"}
        return {"success": True, "data": {"uuid": uuid, "done": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to mark task done: {exc}"}


# ── Delete task ───────────────────────────────────────────────────────────────


@llm_tool(
    name="todo.delete",
    description="Permanently delete a task by UUID.",
    params=[
        {"name": "uuid", "type": "string", "description": "Task UUID to delete", "required": True},
    ],
    permission_level=PermissionLevel.DESTRUCTIVE,
)
def llm_todo_delete(uuid: str = "") -> dict:
    """Delete a task."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_todo_service()
    try:
        ok = service.delete(uuid)
        if not ok:
            return {"success": False, "error": f"Task not found: {uuid}"}
        return {"success": True, "data": {"uuid": uuid, "deleted": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to delete task: {exc}"}
