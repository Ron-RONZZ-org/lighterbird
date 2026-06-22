"""Todo REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from lighterbird.server.deps import get_todo_service
from lighterbird.todo.services import TodoService

router = APIRouter(prefix="/api/v1/todo", tags=["todo"])


@router.get("/todos")
def list_todos(
    status: str | None = None,
    limit: int = 50,
    svc: TodoService = Depends(get_todo_service),
):
    if status:
        todos = svc.search("", status=status, limit=limit)
    else:
        todos = svc.list(limit=limit)
    return {"todos": todos, "total": len(todos)}


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
    }
    todo = svc.create(todo_data)
    return todo


@router.get("/todos/{uuid}")
def get_todo(uuid: str, svc: TodoService = Depends(get_todo_service)):
    todo = svc.get(uuid)
    if not todo:
        raise HTTPException(status_code=404, detail=f"Todo not found: {uuid[:8]}")
    return todo


@router.patch("/todos/{uuid}")
def update_todo(
    uuid: str,
    data: dict,
    svc: TodoService = Depends(get_todo_service),
):
    updates = {}
    field_map = {
        "title": "titolo",
        "description": "priskribo",
        "priority": "prioritato",
        "status": "stato",
        "due": "limdato",
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
