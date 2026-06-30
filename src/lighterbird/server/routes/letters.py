"""Letters REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from lighterbird.server.deps import get_letter_service
from lighterbird.letter.services.letters import LetterService

router = APIRouter(prefix="/api/v1/letters", tags=["letters"])


class RenderPreviewRequest(BaseModel):
    content: str = ""
    format: str = "markdown"


@router.post("/render-preview")
def render_preview(req: RenderPreviewRequest, svc: LetterService = Depends(get_letter_service)):
    """Convert body content to HTML for preview rendering."""
    if not req.content.strip():
        return {"html": ""}
    html = svc.convert_to_html(req.content, req.format)
    return {"html": html}


@router.get("/letters")
def list_letters(
    direction: str | None = None,
    sort: str = "newest",
    group: str | None = None,
    limit: int = 50,
    svc: LetterService = Depends(get_letter_service),
):
    order_by = "created_at"
    desc = True
    if sort == "oldest":
        desc = False
    elif sort == "sender":
        order_by = "sender_manual"
        desc = False

    if group == "conversation":
        raw = svc.list_grouped(limit=limit)
    else:
        raw = svc.list(limit=limit, direction=direction, order_by=order_by, desc=desc)
    letters = [dict(l) for l in raw]
    return {"letters": letters, "total": len(letters)}


@router.post("/letters", status_code=201)
def create_letter(
    data: dict,
    svc: LetterService = Depends(get_letter_service),
):
    letter_data = {
        "direction": data.get("direction", "received"),
        "object": data.get("object", ""),
        "sender_manual": data.get("sender_manual", ""),
        "sender_profile": data.get("sender_profile"),
        "recipient_manual": data.get("recipient_manual", ""),
        "recipient_contact": data.get("recipient_contact"),
        "respond_to_uuid": data.get("respond_to_uuid"),
    }
    letter = svc.create(letter_data)

    body = data.get("body", "")
    if body:
        body_format = data.get("body_format", "html")
        html_content = svc.convert_to_html(body, body_format) if body_format != "html" else body
        svc.store_body(letter["uuid"], html_content)

    return dict(letter)


@router.get("/letters/{uuid}")
def get_letter(uuid: str, svc: LetterService = Depends(get_letter_service)):
    letter = svc.get_with_thread(uuid)
    if not letter:
        raise HTTPException(status_code=404, detail=f"Letter not found: {uuid[:8]}")
    return dict(letter)


@router.get("/letters/{uuid}/body")
def get_letter_body(uuid: str, svc: LetterService = Depends(get_letter_service)):
    letter = svc.get(uuid)
    if not letter:
        raise HTTPException(status_code=404, detail=f"Letter not found: {uuid[:8]}")
    body = svc.get_body(uuid)
    return {"uuid": uuid, "body": body, "body_format": letter.get("body_format", "html")}


@router.delete("/letters/{uuid}", status_code=204)
def delete_letter(uuid: str, svc: LetterService = Depends(get_letter_service)):
    svc.delete(uuid)
