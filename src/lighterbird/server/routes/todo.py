"""Todo REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from lighterbird.server.deps import get_todo_service
from lighterbird.server.command.response import normalize_todo
from lighterbird.todo.services import TodoService

router = APIRouter(prefix="/api/v1/todo", tags=["todo"])


# ── List / Tree ──────────────────────────────────────────────────────


@router.get("/todos")
def list_todos(
    status: str | None = None,
    tree: bool = False,
    limit: int = 50,
    tags: str | None = None,
    sort: str | None = None,
    svc: TodoService = Depends(get_todo_service),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    if tree:
        flat = svc.flatten_tree()
        todos = [normalize_todo(t) for t in flat]
        return {"todos": todos, "total": len(todos), "tree": True}
    todos = svc.search("", status=status, limit=limit, tags=tag_list, sort=sort)
    return {"todos": [normalize_todo(t) for t in todos], "total": len(todos)}


@router.get("/todos/search-titles")
def search_todo_titles(
    q: str = Query("", min_length=1),
    svc: TodoService = Depends(get_todo_service),
):
    """Search todo titles for autocomplete — returns uuid + title only."""
    results = svc.search_titles(q, limit=20)
    return {"results": results}


# ── CRUD ─────────────────────────────────────────────────────────────


@router.post("/todos", status_code=201)
def create_todo(
    data: dict,
    svc: TodoService = Depends(get_todo_service),
):
    todo_data = {
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "priority": data.get("priority", 5),
        "status": "pending",
        "due_date": data.get("due", ""),
        "parent_uuid": data.get("parent_uuid"),
        "template_uuid": data.get("template_uuid"),
    }
    todo = svc.create(todo_data)
    return normalize_todo(todo)


@router.get("/todos/{uuid}")
def get_todo(uuid: str, svc: TodoService = Depends(get_todo_service)):
    todo = svc.get_with_children(uuid)
    if not todo:
        raise HTTPException(
            status_code=404, detail=f"Todo not found: {uuid[:8]}",
        )
    # Normalize the main todo (children already normalized via get_with_children)
    result = normalize_todo(todo)
    # Include dependencies and attachments
    result["dependencies"] = [
        normalize_todo(t) for t in svc.get_dependencies(todo["uuid"])
    ]
    result["blocked_tasks"] = [
        normalize_todo(t) for t in svc.get_blocked_tasks(todo["uuid"])
    ]
    result["attachments"] = svc.get_attachments(todo["uuid"])
    return result


@router.patch("/todos/{uuid}")
def update_todo(
    uuid: str,
    data: dict,
    svc: TodoService = Depends(get_todo_service),
):
    updates: dict = {}
    field_map = {
        "title": "title",
        "description": "description",
        "priority": "priority",
        "status": "status",
        "due": "due_date",
        "parent_uuid": "parent_uuid",
    }
    for json_key, db_key in field_map.items():
        if json_key in data:
            updates[db_key] = data[json_key]
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = svc.update(uuid, updates)
    return normalize_todo(result)


@router.post("/todos/{uuid}/done")
def mark_todo_done(uuid: str, svc: TodoService = Depends(get_todo_service)):
    svc.mark_done(uuid)
    return {"status": "done"}


@router.delete("/todos/{uuid}", status_code=204)
def delete_todo(uuid: str, svc: TodoService = Depends(get_todo_service)):
    svc.delete(uuid)


# ── Dependencies ─────────────────────────────────────────────────────


@router.post("/todos/{uuid}/dependencies")
def add_todo_dependency(
    uuid: str,
    data: dict,
    svc: TodoService = Depends(get_todo_service),
):
    depends_on = data.get("depends_on")
    if not depends_on:
        raise HTTPException(status_code=400, detail="Missing depends_on")
    try:
        svc.add_dependency(uuid, depends_on)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "ok"}


@router.delete("/todos/{uuid}/dependencies/{dep_uuid}")
def remove_todo_dependency(
    uuid: str,
    dep_uuid: str,
    svc: TodoService = Depends(get_todo_service),
):
    svc.remove_dependency(uuid, dep_uuid)
    return {"status": "ok"}


@router.get("/todos/{uuid}/dependencies")
def get_todo_dependencies(
    uuid: str,
    svc: TodoService = Depends(get_todo_service),
):
    deps = [normalize_todo(t) for t in svc.get_dependencies(uuid)]
    blocked = [normalize_todo(t) for t in svc.get_blocked_tasks(uuid)]
    return {"dependencies": deps, "blocked_tasks": blocked}


# ── Attachments ──────────────────────────────────────────────────────


@router.post("/todos/{uuid}/attachments")
def add_todo_attachment(
    uuid: str,
    data: dict,
    svc: TodoService = Depends(get_todo_service),
):
    attachment = svc.add_attachment(
        uuid,
        origina_nomo=data.get("name", "file"),
        original_path=data.get("source", ""),
        cache_path=data.get("cache_path", ""),
        mime_type=data.get("mime_type", ""),
        size=data.get("size", 0),
        md5_checksum=data.get("md5", ""),
    )
    return attachment


@router.delete("/todos/{uuid}/attachments/{att_uuid}")
def remove_todo_attachment(
    uuid: str,
    att_uuid: str,
    svc: TodoService = Depends(get_todo_service),
):
    svc.remove_attachment(att_uuid)
    return {"status": "ok"}


# ── Markdown Export / Import ─────────────────────────────────────────


@router.get("/export-md/{uuid}")
def export_todo_md(
    uuid: str,
    svc: TodoService = Depends(get_todo_service),
):
    """Export a single todo (with tree hierarchy) as Markdown."""
    result = svc.export_md(uuid=uuid)
    if not result:
        raise HTTPException(
            status_code=404, detail=f"Todo not found: {uuid[:8]}",
        )
    return PlainTextResponse(result, media_type="text/markdown")


@router.get("/export-md")
def export_todos_md(
    uuids: str | None = Query(None, description="Comma-separated UUIDs"),
    svc: TodoService = Depends(get_todo_service),
):
    """Export one or more todos as Markdown.

    If ``uuids`` is omitted, exports all todos.
    """
    if uuids:
        uuid_list = [u.strip() for u in uuids.split(",") if u.strip()]
        result = svc.export_md(uuids=uuid_list)
    else:
        result = svc.export_md()
    return PlainTextResponse(result, media_type="text/markdown")


@router.post("/import-md")
def import_todo_md(
    data: dict,
    svc: TodoService = Depends(get_todo_service),
):
    """Import todos from a .md file path.

    Expects ``{"path": "/path/to/todos.md"}``.
    """
    path = data.get("path", "")
    if not path:
        raise HTTPException(status_code=400, detail="Missing 'path' field")
    try:
        created = svc.import_md(path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"created": created, "count": len(created)}


# ── Templates ────────────────────────────────────────────────────────


@router.get("/templates")
def list_templates(
    svc: TodoService = Depends(get_todo_service),
):
    templates = svc.list_templates()
    return {"templates": templates}


@router.get("/templates/{name}")
def get_template(
    name: str,
    svc: TodoService = Depends(get_todo_service),
):
    tpl = svc.get_template_by_name(name)
    if not tpl:
        raise HTTPException(
            status_code=404, detail=f"Template not found: {name}",
        )
    return tpl


@router.post("/templates", status_code=201)
def create_template(
    data: dict,
    svc: TodoService = Depends(get_todo_service),
):
    try:
        tpl = svc.create_template(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return tpl


@router.patch("/templates/{name}")
def update_template(
    name: str,
    data: dict,
    svc: TodoService = Depends(get_todo_service),
):
    tpl = svc.get_template_by_name(name)
    if not tpl:
        raise HTTPException(
            status_code=404, detail=f"Template not found: {name}",
        )
    updated = svc.update_template(tpl["uuid"], data)
    return updated


@router.delete("/templates/{name}", status_code=204)
def delete_template(
    name: str,
    svc: TodoService = Depends(get_todo_service),
):
    tpl = svc.get_template_by_name(name)
    if not tpl:
        raise HTTPException(
            status_code=404, detail=f"Template not found: {name}",
        )
    svc.delete_template(tpl["uuid"])
