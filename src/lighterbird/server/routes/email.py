"""Email REST API routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from lighterbird.server.deps import get_email_service
from lighterbird.server.schemas import (
    AccountCreate, AccountUpdate, AccountResponse, AccountListResponse,
    SyncRequest, SyncResultResponse, SyncAllResponse,
    SendRequest, MarkReadRequest,
    BatchDeleteRequest, BatchMoveRequest, BatchResultResponse,
    ErrorResponse,
)
from lighterbird.email.service import EmailService
from lighterbird.email.server_detect import detect_servers

router = APIRouter(prefix="/api/v1/email", tags=["email"])


def _account_to_response(acct: dict) -> AccountResponse:
    return AccountResponse(
        uuid=acct["uuid"],
        email=acct.get("retposto", ""),
        name=acct.get("nomo", ""),
        imap_server=acct.get("imap_servilo", ""),
        imap_port=acct.get("imap_haveno", 993),
        smtp_server=acct.get("smtp_servilo", ""),
        smtp_port=acct.get("smtp_haveno", 587),
        created_at=acct.get("kreita_je", ""),
        modified_at=acct.get("modifita_je", ""),
    )


@router.get("/accounts", response_model=AccountListResponse)
def list_accounts(email_svc: EmailService = Depends(get_email_service)):
    accounts = email_svc.list_accounts()
    return AccountListResponse(
        accounts=[_account_to_response(a) for a in accounts]
    )


@router.post("/accounts", response_model=AccountResponse, status_code=201)
def create_account(
    data: AccountCreate,
    email_svc: EmailService = Depends(get_email_service),
):
    # Auto-detect IMAP/SMTP servers
    detected = detect_servers(
        data.email,
        imap_server=data.imap_server,
        smtp_server=data.smtp_server,
    )
    acct_data = {
        "nomo": data.name or data.email.split("@")[0],
        "retposto": data.email,
        "imap_servilo": detected["imap"],
        "imap_haveno": data.imap_port,
        "imap_ssl": 1 if data.imap_ssl else 0,
        "smtp_servilo": detected["smtp"],
        "smtp_haveno": data.smtp_port,
        "smtp_tls": 1 if data.smtp_tls else 0,
        "imap_uzantonomo": data.email,
        "smtp_uzantonomo": data.email,
    }
    acct = email_svc.create_account(acct_data, data.password)
    return _account_to_response(acct)


@router.patch("/accounts/{uuid}")
def update_account(
    uuid: str,
    data: AccountUpdate,
    email_svc: EmailService = Depends(get_email_service),
):
    """Update an email account (partial)."""
    acct = email_svc.get_account(uuid)
    if not acct:
        raise HTTPException(status_code=404, detail=f"Account not found: {uuid[:8]}")

    updates = {}
    if data.name is not None:
        updates["nomo"] = data.name
    if data.imap_server is not None:
        updates["imap_servilo"] = data.imap_server
    if data.smtp_server is not None:
        updates["smtp_servilo"] = data.smtp_server
    if updates:
        email_svc.accounts.update(uuid, updates)
    if data.password is not None:
        email_svc.accounts.set_password(uuid, data.password)

    return {"status": "updated", "uuid": uuid[:8]}


@router.delete("/accounts/{uuid}")
def delete_account(uuid: str, email_svc: EmailService = Depends(get_email_service)):
    deleted = email_svc.delete_account(uuid)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Account not found: {uuid[:8]}")
    return {"status": "deleted"}


@router.post("/sync", response_model=SyncResultResponse)
def sync_email(
    req: SyncRequest = SyncRequest(),
    email_svc: EmailService = Depends(get_email_service),
):
    if req.account_uuid:
        result = email_svc.sync_account(req.account_uuid)
        return SyncResultResponse(
            total=result.total, new=result.new, errors=result.errors
        )
    else:
        results = email_svc.sync_all()
        # Return aggregated result
        total = sum(r.get("total", 0) for r in results.values())
        new = sum(r.get("new", 0) for r in results.values())
        errors = []
        for r in results.values():
            errors.extend(r.get("errors", []))
        return SyncResultResponse(total=total, new=new, errors=errors)


@router.get("/folders")
def list_folders(email_svc: EmailService = Depends(get_email_service)):
    """List all known folders with account info."""
    from lighterbird.server.command.response import normalize_account
    # Get all accounts first to map account UUIDs to emails
    accounts = {a["uuid"]: normalize_account(a) for a in email_svc.list_accounts()}
    # Query folders
    rows = list(email_svc.db.execute(
        "SELECT d.uuid, d.nomo, d.konto_id FROM dosierujoj d ORDER BY d.konto_id, d.nomo"
    ))
    folders = []
    for row in rows:
        acct = accounts.get(row["konto_id"], {})
        acct_email = acct.get("email", row["konto_id"][:8] if row["konto_id"] else "")
        folders.append({
            "folder_uuid": row["uuid"],
            "folder_name": row["nomo"],
            "account_uuid": row["konto_id"],
            "account_email": acct_email,
            "label": f"{acct_email}/{row['nomo']}",
        })
    return {"folders": folders}


@router.get("/messages")
def list_messages(
    account_uuid: str | None = Query(default=None, alias="account_uuid"),
    folder: str | None = None,
    query: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    subject: str | None = None,
    after: str | None = None,
    before: str | None = None,
    read: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    email_svc: EmailService = Depends(get_email_service),
):
    from lighterbird.server.command.response import normalize_message
    filters = {}
    if query:
        filters["query"] = query
    if from_:
        filters["from"] = from_
    if subject:
        filters["subject"] = subject
    if after:
        filters["after"] = after
    if before:
        filters["before"] = before
    if read is not None:
        filters["read"] = read
    if account_uuid:
        filters["account"] = account_uuid
    if folder:
        filters["folder"] = folder
    if filters:
        msgs = email_svc.search_messages(filters, limit=limit)
    else:
        msgs = email_svc.list_messages(limit=limit, offset=offset)
    return {"messages": [normalize_message(m) for m in msgs], "total": len(msgs)}


@router.get("/messages/{uuid}")
def get_message(uuid: str, email_svc: EmailService = Depends(get_email_service)):
    from lighterbird.server.command.response import normalize_message
    msg = email_svc.get_message(uuid)
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Message not found: {uuid[:8]}")
    return normalize_message(msg)


_EMAIL_HTML_TMPL = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{subject} — lighterbird</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #1a1a2e; color: #e0e0e0; padding: 1.5rem; line-height: 1.5;
    }}
    .header {{ margin-bottom: 1.5rem; }}
    .header h1 {{ font-size: 1.2rem; color: #e0e0e0; margin-bottom: 0.5rem; }}
    .field {{ display: flex; gap: 0.5rem; padding: 0.2rem 0; font-size: 0.85rem; }}
    .label {{ color: #7c7c9a; min-width: 5rem; flex-shrink: 0; }}
    .value {{ color: #e0e0e0; }}
    hr {{ border: none; border-top: 1px solid #333; margin: 1rem 0; }}
    .body {{ color: #ccc; white-space: pre-wrap; font-family: monospace; font-size: 0.85rem; line-height: 1.6; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>{subject}</h1>
    <div class="field"><span class="label">From</span><span class="value">{from_addr}</span></div>
    <div class="field"><span class="label">To</span><span class="value">{to_addr}</span></div>
    <div class="field"><span class="label">Date</span><span class="value">{date}</span></div>
  </div>
  <hr>
  <div class="body">{body}</div>
</body>
</html>
"""


@router.get("/messages/{uuid}/view", response_class=HTMLResponse)
def view_message_html(uuid: str, email_svc: EmailService = Depends(get_email_service)):
    """Render an email as a standalone HTML page (opens in a new tab)."""
    import html as html_mod
    import json as json_mod

    msg = email_svc.get_message(uuid)
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Message not found: {uuid[:8]}")

    # Parse JSON list fields
    for field in ("al", "kc"):
        raw = msg.get(field, "[]")
        if isinstance(raw, str):
            try:
                msg[field] = json_mod.loads(raw) if raw.strip() else []
            except (json_mod.JSONDecodeError, TypeError):
                msg[field] = []

    to_raw = msg.get("al", [])
    to_str = ", ".join(to_raw) if isinstance(to_raw, list) else str(to_raw)

    subject = html_mod.escape(msg.get("subjekto", "(no subject)"))
    from_addr = html_mod.escape(msg.get("de", ""))
    to_addr = html_mod.escape(to_str)
    date = html_mod.escape(msg.get("ricevita_je", ""))
    body = html_mod.escape(msg.get("korpo", "(no body)"))

    return HTMLResponse(
        _EMAIL_HTML_TMPL.format(
            subject=subject, from_addr=from_addr,
            to_addr=to_addr, date=date, body=body,
        )
    )


@router.get("/messages/{uuid}/conversation")
def get_conversation(uuid: str, limit: int = 20, email_svc: EmailService = Depends(get_email_service)):
    """Get all messages in the same conversation thread as the given message."""
    from lighterbird.server.command.response import normalize_message
    msgs = email_svc.get_conversation(uuid, limit=limit)
    return {"messages": [normalize_message(m) for m in msgs], "total": len(msgs)}


@router.post("/send", status_code=201)
def send_email(
    req: SendRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    try:
        email_svc.send_email(req.account_uuid, req.to, req.subject, req.body, cc=req.cc)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "sent"}


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
    for uuid in req.uuids:
        email_svc.trash_message(uuid)
    return BatchResultResponse(status="ok", count=len(req.uuids))


@router.post("/messages/batch-move", response_model=BatchResultResponse)
def batch_move(
    req: BatchMoveRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Move multiple messages to a destination folder."""
    # Validate destination folder exists
    folder = email_svc.db.execute_one(
        "SELECT uuid FROM dosierujoj WHERE uuid = ?",
        (req.destination_folder_uuid,),
    )
    if not folder:
        raise HTTPException(
            status_code=404,
            detail=f"Destination folder '{req.destination_folder_uuid[:8]}' not found. "
                   f"Sync your email accounts first with !sync --email.",
        )
    for uuid in req.uuids:
        email_svc.move_message(uuid, req.destination_folder_uuid)
    return BatchResultResponse(status="ok", count=len(req.uuids))
