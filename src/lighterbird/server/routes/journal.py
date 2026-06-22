"""Journal REST API routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from lighterbird.server.deps import get_journal_service
from lighterbird.journal.services import JournalService

router = APIRouter(prefix="/api/v1/journal", tags=["journal"])


@router.get("/entries")
def list_entries(
    date_str: str | None = None,
    query: str | None = None,
    limit: int = 50,
    svc: JournalService = Depends(get_journal_service),
):
    if date_str:
        entries = svc.list_by_date(date_str)
    elif query:
        entries = svc.search(query, limit=limit)
    else:
        entries = svc.list(limit=limit)
    return {"entries": entries, "total": len(entries)}


@router.post("/entries", status_code=201)
def create_entry(
    data: dict,
    svc: JournalService = Depends(get_journal_service),
):
    entry_data = {
        "titolo": data.get("title", ""),
        "teksto": data.get("text", ""),
        "dato": data.get("date", date.today().isoformat()),
    }
    entry = svc.create(entry_data)
    return entry


@router.get("/entries/{uuid}")
def get_entry(uuid: str, svc: JournalService = Depends(get_journal_service)):
    entry = svc.get(uuid)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Entry not found: {uuid[:8]}")
    return entry


@router.patch("/entries/{uuid}")
def update_entry(
    uuid: str,
    data: dict,
    svc: JournalService = Depends(get_journal_service),
):
    updates = {}
    field_map = {
        "title": "titolo",
        "text": "teksto",
        "date": "dato",
    }
    for json_key, db_key in field_map.items():
        if json_key in data:
            updates[db_key] = data[json_key]
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = svc.update(uuid, updates)
    return result


@router.delete("/entries/{uuid}", status_code=204)
def delete_entry(uuid: str, svc: JournalService = Depends(get_journal_service)):
    svc.delete(uuid)
