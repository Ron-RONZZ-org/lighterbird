"""Todo REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

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
    svc: TodoService = Depends(get_todo_service),
):
    if tree:
        flat = svc.flatten_tree()
        todos = [normalize_todo(t) for t in flat]
        return {"todos": todos, "total": len(todos), "tree": True}
    if status:
        todos = svc.search("", status=status, limit=limit)
    else:
        todos = svc.list(limit=limit)
    return {"todos": todos, "total": len(todos)}


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
        "titolo": data.get("title", ""),
        "priskribo": data.get("description", ""),
        "prioritato": data.get("priority", 5),
        "stato": "pending",
        "limdato": data.get("due", ""),
        "parent_uuid": data.get("parent_uuid"),
        "shablono_uuid": data.get("template_uuid"),
    }
    todo = svc.create(todo_data)
    return todo


@router.get("/todos/{uuid}")
def get_todo(uuid: str, svc: TodoService = Depends(get_todo_service)):
    todo = svc.get_with_children(uuid)
    if not todo:
        raise HTTPException(
            status_code=404, detail=f"Todo not found: {uuid[:8]}",
        )
    # Include dependencies and attachments
    todo["dependencies"] = [
        normalize_todo(t) for t in svc.get_dependencies(todo["uuid"])
    ]
    todo["blocked_tasks"] = [
        normalize_todo(t) for t in svc.get_blocked_tasks(todo["uuid"])
    ]
    todo["attachments"] = svc.get_attachments(todo["uuid"])
    return todo


@router.patch("/todos/{uuid}")
def update_todo(
    uuid: str,
    data: dict,
    svc: TodoService = Depends(get_todo_service),
):
    updates: dict = {}
    field_map = {
        "title": "titolo",
        "description": "priskribo",
        "priority": "prioritato",
        "status": "stato",
        "due": "limdato",
        "parent_uuid": "parent_uuid",
    }
    for json_key, db_key in field_map.items():
        if json_key in data:
            updates[db_key] = data[json_key]
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = svc.update(uuid, updates)
    return result


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
        origina_vojo=data.get("source", ""),
        kasko_vojo=data.get("cache_path", ""),
        dosier_peco=data.get("mime_type", ""),
        grandeco=data.get("size", 0),
        md5_cheksumo=data.get("md5", ""),
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
