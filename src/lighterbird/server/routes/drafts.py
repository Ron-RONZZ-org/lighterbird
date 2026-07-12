"""API routes for saving/loading drafts from the frontend (Ctrl+S)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lighterbird.core.drafts import delete_draft, get_draft, list_drafts, save_draft
from lighterbird.server.deps import get_email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/drafts", tags=["drafts"])


class DraftSaveRequest(BaseModel):
    domain: str = Field(..., pattern=r"^(email|journal|todo|calendar-event|letter)$")
    title: str = ""
    data: dict = Field(default_factory=dict)
    uuid: str | None = None


class DraftSaveResponse(BaseModel):
    uuid: str
    title: str
    domain: str
    updated_at: str
    imap_error: str | None = None  # populated when IMAP DRAFTS sync fails


class DraftListItem(BaseModel):
    uuid: str
    title: str
    domain: str
    updated: str


class DraftListResponse(BaseModel):
    drafts: list[DraftListItem]


@router.post("", response_model=DraftSaveResponse)
def save_draft_endpoint(body: DraftSaveRequest,
                        email_svc=Depends(get_email_service)) -> DraftSaveResponse:
    """Save (create or update) a draft."""
    draft = save_draft(body.domain, body.title, body.data, draft_uuid=body.uuid)
    # Best-effort sync of email drafts to IMAP DRAFTS folder
    imap_error = None
    if body.domain == "email":
        try:
            imap_error = email_svc.save_draft_to_imap(draft)
        except Exception as exc:
            imap_error = str(exc)
            logger.exception("Failed to sync email draft %s to IMAP DRAFTS", draft.get("uuid", "?")[:8])
    return DraftSaveResponse(
        uuid=draft["uuid"],
        title=draft.get("title", ""),
        domain=draft["domain"],
        updated_at=draft.get("updated_at", ""),
        imap_error=imap_error,
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
def delete_draft_endpoint(draft_uuid: str,
                          email_svc=Depends(get_email_service)) -> dict:
    """Delete a draft by UUID.

    For email drafts with a known IMAP presence, enqueues an ``expunge``
    backlog operation to remove the draft from the IMAP DRAFTS folder.
    """
    draft = get_draft(draft_uuid)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # For email drafts, clean up IMAP presence
    if draft.get("domain") == "email":
        # Look up IMAP UID from the uid map
        row = email_svc.db.execute_one(
            "SELECT imap_uid, folder_name, account_email FROM email_draft_uid_map "
            "WHERE draft_uuid = ?",
            (draft_uuid,),
        )
        if row and row["imap_uid"] is not None:
            # Enqueue IMAP deletion via backlog (soft-delete + expunge)
            email_svc.msg_ops.backlog.enqueue(
                msg_uuid=draft_uuid,
                account_email=row["account_email"],
                folder_name=row["folder_name"],
                imap_uid=row["imap_uid"],
                is_read=1,
                is_deleted=1,
                operation="expunge",
            )

        # Clean up UID map entry
        email_svc.db.execute(
            "DELETE FROM email_draft_uid_map WHERE draft_uuid = ?",
            (draft_uuid,),
        )

    delete_draft(draft_uuid)
    return {"deleted": True}
