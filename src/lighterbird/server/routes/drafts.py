"""API routes for saving/loading drafts from the frontend (Ctrl+S)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from lighterbird.core.drafts import get_draft, save_draft, list_drafts, delete_draft

router = APIRouter(prefix="/api/v1/drafts", tags=["drafts"])


class DraftSaveRequest(BaseModel):
    domain: str = Field(..., pattern=r"^(email|journal|todo|calendar-event)$")
    title: str = ""
    data: dict = Field(default_factory=dict)
    uuid: str | None = None


class DraftSaveResponse(BaseModel):
    uuid: str
    title: str
    domain: str
    updated_at: str


class DraftListItem(BaseModel):
    uuid: str
    title: str
    domain: str
    updated: str


class DraftListResponse(BaseModel):
    drafts: list[DraftListItem]


@router.post("", response_model=DraftSaveResponse)
def save_draft_endpoint(body: DraftSaveRequest) -> DraftSaveResponse:
    """Save (create or update) a draft."""
    draft = save_draft(body.domain, body.title, body.data, draft_uuid=body.uuid)
    return DraftSaveResponse(
        uuid=draft["uuid"],
        title=draft.get("title", ""),
        domain=draft["domain"],
        updated_at=draft.get("updated_at", ""),
    )


@router.get("", response_model=DraftListResponse)
def list_drafts_endpoint(domain: str | None = None) -> DraftListResponse:
    """List all drafts, optionally filtered by domain."""
    drafts = list_drafts(domain)
    return DraftListResponse(
        drafts=[
            DraftListItem(
                uuid=d["uuid"],
                title=d.get("title", ""),
                domain=d.get("domain", ""),
                updated=d.get("updated_at", "")[:16].replace("T", " "),
            )
            for d in drafts
        ]
    )


@router.get("/{draft_uuid}")
def get_draft_endpoint(draft_uuid: str):
    """Get a single draft by UUID."""
    draft = get_draft(draft_uuid)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.delete("/{draft_uuid}")
def delete_draft_endpoint(draft_uuid: str) -> dict:
    """Delete a draft by UUID."""
    if not delete_draft(draft_uuid):
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"deleted": True}
