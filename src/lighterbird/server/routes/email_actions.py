"""Email action REST API routes — send, trash, batch ops, import/export, attachments.

Extracted from email.py for AGENTS.md file-size compliance (<500 lines).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from lighterbird.email.service import EmailService
from lighterbird.server.deps import get_contact_service, get_email_service
from lighterbird.server.schemas import (
    BatchDeleteRequest,
    BatchMoveRequest,
    BatchResultResponse,
    MarkReadRequest,
    SendRequest,
)

router = APIRouter(prefix="/api/v1/email", tags=["email"])


@router.post("/send", status_code=201)
def send_email(
    req: SendRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    try:
        result = email_svc.send_email(
            req.account_email, req.to, req.subject, req.body,
            cc=req.cc, bcc=req.bcc, priority=req.priority,
            body_format=req.body_format, attachments=req.attachments,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": result.get("status", "sent")}


@router.patch("/messages/{uuid}/read")
def mark_read(
    uuid: str,
    req: MarkReadRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    email_svc.mark_read(uuid, req.read)
    return {"status": "ok"}


@router.post("/messages/{uuid}/trash")
def trash_message(
    uuid: str,
    email_svc: EmailService = Depends(get_email_service),
):
    """Soft-delete a single message."""
    email_svc.trash_message(uuid)
    return {"status": "trashed"}


@router.post("/messages/batch-delete", response_model=BatchResultResponse)
def batch_delete(
    req: BatchDeleteRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Soft-delete multiple messages at once."""
    result = email_svc.msg_ops.batch_trash_messages(req.uuids)
    return BatchResultResponse(
        status="ok",
        count=result["count"],
    )


@router.post("/messages/batch-move", response_model=BatchResultResponse)
def batch_move(
    req: BatchMoveRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Move multiple messages to a destination folder."""
    for uuid in req.uuids:
        email_svc.move_message(uuid, req.destination_folder)
    return BatchResultResponse(status="ok", count=len(req.uuids))


@router.get("/export-eml/{uuid}")
def export_eml(uuid: str, email_svc: EmailService = Depends(get_email_service)):
    """Export a message as .eml (RFC 822) download."""
    eml_text = email_svc.export_eml(uuid)
    if eml_text is None:
        raise HTTPException(status_code=404, detail=f"Message not found: {uuid[:8]}")
    msg = email_svc.get_message(uuid)
    subject = (msg or {}).get("subject", "") or ""
    base = re.sub(r'[^a-zA-Z0-9_-]', '', subject)[:48] or uuid[:12]
    filename = f"{base}.eml"
    return Response(
        content=eml_text.encode("utf-8"),
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/messages/{uuid}/attachments")
def list_attachments(
    uuid: str,
    email_svc: EmailService = Depends(get_email_service),
):
    """List all attachments for a given message."""
    from lighterbird.core.storage import AttachmentStore

    rows = list(email_svc.db.execute(
        "SELECT uuid, filename, mime_type, size, content_id, storage_path "
        "FROM email_attachments WHERE message_uuid = ? ORDER BY filename",
        (uuid,),
    ))
    store = AttachmentStore()
    attachments = []
    for row in rows:
        file_exists = False
        try:
            store.retrieve(uuid, row["content_id"])
            file_exists = True
        except FileNotFoundError:
            pass
        attachments.append({
            "uuid": row["uuid"],
            "filename": row["filename"],
            "mime_type": row["mime_type"],
            "size": row["size"],
            "content_id": row["content_id"],
            "available": file_exists,
        })
    return {"attachments": attachments}


@router.get("/attachments/{att_uuid}/download")
def download_attachment(
    att_uuid: str,
    email_svc: EmailService = Depends(get_email_service),
):
    """Download a single attachment by its UUID."""
    from fastapi.responses import Response as FastResponse

    from lighterbird.core.storage import AttachmentStore

    row = email_svc.db.execute_one(
        "SELECT message_uuid, filename, mime_type, content_id "
        "FROM email_attachments WHERE uuid = ?",
        (att_uuid,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Attachment not found: {att_uuid[:8]}")

    store = AttachmentStore()
    try:
        data = store.retrieve(row["message_uuid"], row["content_id"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Attachment file not found on disk.")

    mime = row["mime_type"] or "application/octet-stream"
    filename = row["filename"] or "attachment"
    return FastResponse(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import-eml", status_code=201)
def import_eml(data: dict, email_svc: EmailService = Depends(get_email_service)):
    """Import a .eml file as an email draft."""
    path = data.get("path", "")
    if not path:
        raise HTTPException(status_code=400, detail="Path is required.")
    try:
        draft = email_svc.import_eml(path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"imported": 1, "uuid": draft["uuid"]}


@router.post("/messages/{uuid}/add-contacts")
def add_contacts_from_email(uuid: str):
    """Extract sender from a message and create a contact.

    Returns existing contact UUID if already present (idempotent).
    """
    email_svc = get_email_service()
    msg = email_svc.get_message(uuid)
    if not msg:
        raise HTTPException(status_code=404, detail=f"Message not found: {uuid[:8]}")

    from_addr = (msg.get("from_addr") or "").strip()
    if not from_addr or "@" not in from_addr:
        raise HTTPException(status_code=400, detail="Message has no valid sender address.")

    # Parse name and email from "Name <email>" format
    name = ""
    email = from_addr
    m = re.match(r"^(.*?)\s*<([^>]+)>$", from_addr)
    if m:
        name = m.group(1).strip().strip('"')
        email = m.group(2).strip()

    contact_svc = get_contact_service()

    # Check if contact already exists by email
    existing = contact_svc.find_by_email(email)
    if existing:
        return {"contact": existing, "created": False, "uuid": existing["uuid"]}

    # Split name into given/family
    parts = name.split(None, 1) if name else [email.split("@")[0]]
    given_name = parts[0] if parts else email.split("@")[0]
    family_name = parts[1] if len(parts) > 1 else ""

    import json
    contact_data = {
        "given_name": given_name,
        "family_name": family_name,
        "emails": json.dumps([{"value": email, "tag": ""}]),
        "phones": "[]",
    }
    contact = contact_svc.create(contact_data)
    return {"contact": contact, "created": True, "uuid": contact["uuid"]}
