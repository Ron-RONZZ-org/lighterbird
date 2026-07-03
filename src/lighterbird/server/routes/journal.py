"""Journal REST API routes."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from lighterbird.server.deps import get_journal_service
from lighterbird.server.command.response import normalize_journal_entry
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
        raw = svc.list_by_date(date_str)
    elif query:
        raw = svc.search(query, limit=limit)
    else:
        raw = svc.list(limit=limit)
    entries = [normalize_journal_entry(e) for e in raw]
    return {"entries": entries, "total": len(entries)}


@router.post("/entries", status_code=201)
def create_entry(
    data: dict,
    svc: JournalService = Depends(get_journal_service),
):
    entry_data = {
        "title": data.get("title", ""),
        "text": data.get("text", ""),
        "date": data.get("date", date.today().isoformat()),
    }
    entry = svc.create(entry_data)
    return normalize_journal_entry(entry)


@router.get("/entries/{uuid}")
def get_entry(uuid: str, svc: JournalService = Depends(get_journal_service)):
    entry = svc.get(uuid)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Entry not found: {uuid[:8]}")
    return normalize_journal_entry(entry)


@router.patch("/entries/{uuid}")
def update_entry(
    uuid: str,
    data: dict,
    svc: JournalService = Depends(get_journal_service),
):
    updates = {}
    field_map = {
        "title": "title",
        "text": "text",
        "date": "date",
    }
    for json_key, db_key in field_map.items():
        if json_key in data:
            updates[db_key] = data[json_key]
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = svc.update(uuid, updates)
    return normalize_journal_entry(result)


@router.delete("/entries/{uuid}", status_code=204)
def delete_entry(uuid: str, svc: JournalService = Depends(get_journal_service)):
    svc.delete(uuid)


# ── Markdown export / import ──────────────────────────────────────────


class ImportMdRequest(BaseModel):
    path: str


@router.get("/export-md")
def export_md(
    uuids: str | None = Query(None, description="Comma-separated UUIDs"),
    svc: JournalService = Depends(get_journal_service),
):
    """Export one or more journal entries as .md (query param: ``?uuids=u1,u2``)."""
    if not uuids:
        raise HTTPException(status_code=400, detail="Provide ?uuids=uuid1,uuid2")
    ids = [u.strip() for u in uuids.split(",") if u.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="No valid UUIDs provided")
    md = svc.export_md(uuids=ids)
    return {"type": "markdown", "data": md}


@router.get("/export-md/{uuid}")
def export_entry_md(
    uuid: str,
    svc: JournalService = Depends(get_journal_service),
):
    """Export a single journal entry as .md."""
    entry = svc.get(uuid)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Entry not found: {uuid[:8]}")
    md = svc.export_md(uuid=uuid)
    return {"type": "markdown", "data": md}


@router.post("/import-md", status_code=201)
def import_md(
    body: ImportMdRequest,
    svc: JournalService = Depends(get_journal_service),
):
    """Import journal entry(s) from a .md file."""
    try:
        uuids = svc.import_md(body.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}")
    return {"imported": uuids, "count": len(uuids)}
