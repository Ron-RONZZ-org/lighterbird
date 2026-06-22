"""Email REST API routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from lighterbird.server.deps import get_email_service
from lighterbird.server.schemas import (
    AccountCreate, AccountResponse, AccountListResponse,
    SyncRequest, SyncResultResponse, SyncAllResponse,
    SendRequest, MarkReadRequest,
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
    return {"messages": msgs, "total": len(msgs)}


@router.get("/messages/{uuid}")
def get_message(uuid: str, email_svc: EmailService = Depends(get_email_service)):
    msg = email_svc.get_message(uuid)
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Message not found: {uuid[:8]}")
    # Parse JSON list fields
    for field in ("al", "kc"):
        raw = msg.get(field, "[]")
        if isinstance(raw, str):
            try:
                msg[field] = json.loads(raw) if raw.strip() else []
            except (json.JSONDecodeError, TypeError):
                msg[field] = []
    return msg


@router.post("/send", status_code=201)
def send_email(
    req: SendRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    email_svc.send_email(req.account_uuid, req.to, req.subject, req.body, cc=req.cc)
    return {"status": "sent"}


@router.patch("/messages/{uuid}/read")
def mark_read(
    uuid: str,
    req: MarkReadRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    email_svc.mark_read(uuid, req.read)
    return {"status": "ok"}
