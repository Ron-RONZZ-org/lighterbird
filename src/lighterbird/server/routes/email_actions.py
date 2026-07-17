"""Email action REST API routes — send, trash, batch ops, import/export, attachments.

Extracted from email.py for AGENTS.md file-size compliance (<500 lines).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from lighterbird.email.service import EmailService
from lighterbird.core.paths import safe_resolve_path
from lighterbird.server.deps import get_email_service
from pydantic import BaseModel, Field

from lighterbird.server.schemas import (
    BatchDeleteRequest,
    BatchMoveRequest,
    BatchResultResponse,
    EmailPreviewRequest,
    EmailPreviewResponse,
    MarkReadRequest,
    SendRequest,
)


class SignatureUpdateRequest(BaseModel):
    name: str | None = Field(default=None, description="New signature name")
    signature_text: str | None = Field(default=None, description="New signature text")
    signature_format: str | None = Field(default=None, description="Signature format: plain, html, or markdown")

    model_config = {"extra": "forbid"}

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
            signature=req.signature,
            signature_format=req.signature_format,
            in_reply_to=req.in_reply_to,
            save_as_sample=req.save_as_sample,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Trigger background SMTP delivery (non-blocking) — the send queue
    # processes immediately on the email worker thread.
    from lighterbird.server.tasks import enqueue_email_send

    enqueue_email_send()
    return {"status": result.get("status", "queued")}


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


@router.post("/trash/clear")
def clear_trash(
    email_svc: EmailService = Depends(get_email_service),
):
    """Permanently delete ALL messages in Trash folders."""
    rows = list(email_svc.db.execute(
        "SELECT uuid FROM messages WHERE folder_name = ? AND is_deleted = 0",
        ("Trash",),
    ))
    uuids = [r["uuid"] for r in rows]
    if not uuids:
        return {"status": "ok", "count": 0}
    result = email_svc.msg_ops.batch_hard_delete_messages(uuids)
    # Process EXPUNGE backlog immediately so IMAP is cleaned up
    # without waiting for the next sync cycle.
    email_svc.msg_ops.process_sync_backlog()
    return {
        "status": "ok" if not result.get("errors") else "partial",
        "count": result["count"],
        "errors": result.get("errors", []),
    }


@router.post("/messages/batch-delete-hard", response_model=BatchResultResponse)
def batch_delete_hard(
    req: BatchDeleteRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Permanently delete multiple messages from local DB and IMAP server."""
    result = email_svc.msg_ops.batch_hard_delete_messages(req.uuids)
    # Process EXPUNGE backlog immediately so IMAP is cleaned up without
    # waiting for the next sync cycle.  Without this, hard-deleted messages
    # get re-inserted on the next IMAP sync (resurrection bug).
    email_svc.msg_ops.process_sync_backlog()
    return BatchResultResponse(
        status="ok" if not result.get("errors") else "partial",
        count=result["count"],
        errors=result.get("errors", []),
    )


@router.post("/messages/batch-move", response_model=BatchResultResponse)
def batch_move(
    req: BatchMoveRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Move multiple messages to a destination folder in one transaction."""
    count = email_svc.batch_move_messages(req.uuids, req.destination_folder)
    return BatchResultResponse(status="ok", count=count)


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
        safe_resolve_path(path)
    except (ValueError, FileNotFoundError, IsADirectoryError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        draft = email_svc.import_eml(path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"imported": 1, "uuid": draft["uuid"]}


@router.post("/preview", response_model=EmailPreviewResponse)
def email_preview(req: EmailPreviewRequest):
    """Compose a full email preview HTML document from its parts.

    Accepts subject, body, body_format, optional signature, and optional
    attachments.  Returns a complete HTML document suitable for rendering
    in the PreviewDialog or in a new browser tab.
    """
    from lighterbird.server.render_utils import compose_email_html

    # Build attachment info for links — extract uuid+filename from each
    att_info = []
    for att in req.attachments or []:
        if isinstance(att, dict):
            att_info.append({
                "uuid": att.get("uuid", ""),
                "filename": att.get("filename", "attachment"),
            })

    html = compose_email_html(
        subject=req.subject,
        body=req.body,
        body_format=req.body_format,
        signature_text=req.signature_text,
        signature_format=req.signature_format,
        attachments=att_info or None,
        attachment_base_url="/api/v1/email/attachments/",
    )
    return EmailPreviewResponse(html=html)


@router.get("/signatures")
def list_signatures(email_svc: EmailService = Depends(get_email_service)):
    """List all configured signatures with account-default enrichment.

    Returns the same data as the ``!email signature list`` CLI command.
    """
    sigs = email_svc.signatures.list_signatures()

    # Enrich each signature with account default info
    accounts = email_svc.list_accounts()
    account_defaults: dict[str, list[str]] = {}
    for acct in accounts:
        default_uuid = email_svc.signatures.get_account_default_uuid(acct["email"])
        if default_uuid:
            account_defaults.setdefault(default_uuid, []).append(acct["email"])

    enriched = []
    for sig in sigs:
        entry = dict(sig)
        default_for = account_defaults.get(sig["uuid"], [])
        if default_for:
            entry["default_for"] = default_for
        enriched.append(entry)

    return {"signatures": enriched}


@router.patch("/signatures/{sig_uuid}")
def update_signature(
    sig_uuid: str,
    data: SignatureUpdateRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Update a signature's name, text, and/or format."""
    try:
        updated = email_svc.signatures.update(
            sig_uuid,
            name=data.name,
            signature_text=data.signature_text,
            signature_format=data.signature_format,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail=f"Signature not found: {sig_uuid}")
    return updated


@router.delete("/signatures/{sig_uuid}")
def delete_signature(
    sig_uuid: str,
    email_svc: EmailService = Depends(get_email_service),
):
    """Delete a signature by UUID."""
    deleted = email_svc.signatures.delete(sig_uuid)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Signature not found: {sig_uuid}")
    return {"status": "deleted", "uuid": sig_uuid}

