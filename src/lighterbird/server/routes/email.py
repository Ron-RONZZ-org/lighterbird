"""Email REST API routes — accounts, sync, folders, messages, conversation.

Action endpoints (send, trash, batch ops, import/export eml, attachments)
live in ``email_actions.py`` — this file is kept under 500 lines.
"""

from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from lighterbird.email.server_detect import detect_servers
from lighterbird.email.service import EmailService
from lighterbird.server.deps import get_email_service
from lighterbird.server.schemas import (
    AccountCreate,
    AccountListResponse,
    AccountResponse,
    AccountUpdate,
    SyncRequest,
    SyncResultResponse,
)

router = APIRouter(prefix="/api/v1/email", tags=["email"])


def _account_to_response(acct: dict) -> AccountResponse:
    return AccountResponse(
        email=acct.get("email", ""),
        name=acct.get("name", ""),
        imap_server=acct.get("imap_server", ""),
        imap_port=acct.get("imap_port", 993),
        smtp_server=acct.get("smtp_server", ""),
        smtp_port=acct.get("smtp_port", 587),
        created_at=acct.get("created_at", ""),
        modified_at=acct.get("updated_at", ""),
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
        "name": data.name or data.email.split("@")[0],
        "email": data.email.lower().strip(),
        "imap_server": detected["imap"],
        "imap_port": data.imap_port,
        "imap_use_ssl": 1 if data.imap_ssl else 0,
        "smtp_server": detected["smtp"],
        "smtp_port": data.smtp_port,
        "smtp_use_tls": 1 if data.smtp_tls else 0,
        "imap_username": data.email,
        "smtp_username": data.email,
    }
    acct = email_svc.create_account(acct_data, data.password)
    return _account_to_response(acct)


@router.patch("/accounts/{email}")
def update_account(
    email: str,
    data: AccountUpdate,
    email_svc: EmailService = Depends(get_email_service),
):
    """Update an email account (partial)."""
    acct = email_svc.get_account(email)
    if not acct:
        raise HTTPException(status_code=404, detail=f"Account not found: {email}")

    updates = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.imap_server is not None:
        updates["imap_server"] = data.imap_server
    if data.smtp_server is not None:
        updates["smtp_server"] = data.smtp_server
    if updates:
        email_svc.accounts.update(email, updates)
    if data.password is not None:
        email_svc.accounts.set_password(email, data.password)

    return {"status": "updated", "email": email}


@router.delete("/accounts/{email}")
def delete_account(email: str, email_svc: EmailService = Depends(get_email_service)):
    deleted = email_svc.delete_account(email)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Account not found: {email}")
    return {"status": "deleted"}


@router.post("/sync", response_model=SyncResultResponse)
def sync_email(
    req: SyncRequest = SyncRequest(),
    email_svc: EmailService = Depends(get_email_service),
):
    if req.account_email:
        result = email_svc.sync_account(req.account_email)
        return SyncResultResponse(
            total=result.total, new=result.new, errors=result.errors
        )
    else:
        results = email_svc.sync_all()
        total = sum(r.get("total", 0) for r in results.values())
        new = sum(r.get("new", 0) for r in results.values())
        errors = []
        for r in results.values():
            errors.extend(r.get("errors", []))
        return SyncResultResponse(total=total, new=new, errors=errors)


@router.get("/folders")
def list_folders(email_svc: EmailService = Depends(get_email_service)):
    """List all known folders with account info."""
    rows = list(email_svc.db.execute(
        "SELECT account_email, name FROM folders ORDER BY account_email, name"
    ))
    folders = []
    for row in rows:
        acct_email = row["account_email"]
        folders.append({
            "folder_name": row["name"],
            "account_email": acct_email,
            "label": f"{acct_email}/{row['name']}",
        })
    return {"folders": folders}


@router.post("/folders")
def create_folder(
    account_email: str = Query(...),
    folder_name: str = Query(...),
    email_svc: EmailService = Depends(get_email_service),
):
    """Create a new IMAP folder on the server.

    Uses the account's IMAP credentials to send the CREATE command.
    On success, also inserts the folder into the local DB.
    """
    accounts = email_svc.list_accounts()
    target = None
    for acct in accounts:
        if acct["email"] == account_email:
            target = acct
            break
    if not target:
        raise HTTPException(status_code=404, detail=f"Account not found: {account_email}")

    # Connect to IMAP and create the folder
    host = target.get("imap_server", "")
    port = target.get("imap_port", 993)
    use_ssl = target.get("imap_use_ssl", True)
    password = email_svc.get_password(account_email)
    if not password:
        raise HTTPException(status_code=400, detail=f"No password configured for account: {account_email}")

    try:
        from lighterbird.email.imap.client import IMAPClient
        client = IMAPClient(host, port, use_ssl)
        client.connect(account_email, password)
        success = client.create_folder(folder_name)
        client.disconnect()
        if not success:
            raise HTTPException(status_code=500, detail=f"IMAP CREATE failed for folder: {folder_name}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create folder: {e}")

    # Insert into local DB
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    try:
        email_svc.db.execute(
            "INSERT OR IGNORE INTO folders (account_email, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (account_email, folder_name, now, now),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save folder to local DB: {e}")

    return {"status": "ok", "folder_name": folder_name, "account_email": account_email}


@router.get("/messages")
def list_messages(
    account_email: str | None = Query(default=None, alias="account_email"),
    folder: str | None = None,
    query: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    subject: str | None = None,
    after: str | None = None,
    before: str | None = None,
    read: bool | None = None,
    sort: str = "newest",
    group: str | None = None,
    limit: int = 50,
    offset: int = 0,
    cursor: str = "",
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
    if account_email:
        filters["account"] = account_email
    if folder:
        # Support comma-separated folder names from the frontend
        filters["folder"] = [f.strip() for f in folder.split(",") if f.strip()]
    if sort:
        filters["sort"] = sort
    if group:
        filters["group"] = group
    if cursor:
        filters["cursor"] = cursor
    # Fetch limit+1 to detect next page
    fetch_limit = limit + 1
    if filters:
        msgs = email_svc.search_messages(filters, limit=fetch_limit)
    else:
        msgs = email_svc.list_messages(limit=fetch_limit, offset=offset, sort=sort)
    has_more = len(msgs) > limit
    if has_more:
        msgs = msgs[:limit]
        last = msgs[-1]
        next_cursor = f"{last.get('received_at', '')}|{last.get('uuid', '')}"
    else:
        next_cursor = ""
    # Enrich messages with attachment count
    uuids = [m["uuid"] for m in msgs if m.get("uuid")]
    att_counts: dict[str, int] = {}
    if uuids:
        placeholders = ",".join("?" for _ in uuids)
        rows = list(email_svc.db.execute(
            f"SELECT message_uuid, COUNT(*) AS cnt FROM email_attachments "
            f"WHERE message_uuid IN ({placeholders}) GROUP BY message_uuid",
            uuids,
        ))
        att_counts = {r["message_uuid"]: r["cnt"] for r in rows}
    enriched = []
    for m in msgs:
        d = dict(m)
        d["attachment_count"] = att_counts.get(m.get("uuid", ""), 0)
        enriched.append(d)
    return {"messages": enriched, "total": len(enriched), "has_more": has_more, "next_cursor": next_cursor}


@router.get("/messages/{uuid}")
def get_message(uuid: str, email_svc: EmailService = Depends(get_email_service)):
    msg = email_svc.get_message(uuid)
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Message not found: {uuid[:8]}")

    # Lazy body fetch: if this message was synced header-only, download the
    # full message body (and attachments) on demand.
    if not msg.get("body_fetched", 1) and msg.get("imap_uid") and msg.get("account_email") and msg.get("folder_name"):
        _lazy_fetch_body(email_svc, msg)

    result = dict(msg)
    # Re-read after potential lazy fetch
    if msg.get("body_fetched") == 0:
        fresh = email_svc.get_message(uuid)
        if fresh:
            result = dict(fresh)

    # Include attachment count
    att_rows = list(email_svc.db.execute(
        "SELECT COUNT(*) AS cnt FROM email_attachments WHERE message_uuid = ?",
        (uuid,),
    ))
    result["attachment_count"] = att_rows[0]["cnt"] if att_rows else 0
    return result


def _lazy_fetch_body(email_svc: EmailService, msg: dict) -> None:
    """Fetch full message body for a header-only synced message."""
    import logging
    logger = logging.getLogger(__name__)

    acct = email_svc.accounts.get_account_with_password(msg["account_email"])
    if not acct or not acct.get("password"):
        logger.warning(
            "lazy_fetch: no password for %s, cannot fetch body",
            msg["account_email"],
        )
        return

    from lighterbird.email.imap.client import IMAPClient

    client = IMAPClient(
        host=acct.get("imap_server", ""),
        port=acct.get("imap_port", 993),
        use_ssl=acct.get("imap_use_ssl", 1) == 1,
    )
    try:
        client.connect(
            username=acct.get("imap_username", "") or msg["account_email"],
            password=acct["password"],
        )
        data = client.fetch_message_body(
            msg["account_email"], msg["folder_name"],
            msg["imap_uid"], email_svc,
        )
        if data is not None:
            logger.info(
                "lazy_fetch: fetched body for %s/%s UID %s",
                msg["account_email"][:20], msg["folder_name"][:20], msg["imap_uid"],
            )
        else:
            logger.warning(
                "lazy_fetch: failed for %s/%s UID %s",
                msg["account_email"][:20], msg["folder_name"][:20], msg["imap_uid"],
            )
    except Exception as exc:
        logger.warning(
            "lazy_fetch: error for %s/%s UID %s: %s",
            msg["account_email"][:20], msg["folder_name"][:20],
            msg["imap_uid"], exc,
        )
    finally:
        client.disconnect()


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
    for field in ("to_recipients", "cc_recipients"):
        raw = msg.get(field, "[]")
        if isinstance(raw, str):
            try:
                msg[field] = json_mod.loads(raw) if raw.strip() else []
            except (json_mod.JSONDecodeError, TypeError):
                msg[field] = []

    to_raw = msg.get("to_recipients", [])
    to_str = ", ".join(to_raw) if isinstance(to_raw, list) else str(to_raw)

    subject = html_mod.escape(msg.get("subject", "(no subject)"))
    from_addr = html_mod.escape(msg.get("from_addr", ""))
    to_addr = html_mod.escape(to_str)
    date = html_mod.escape(msg.get("received_at", ""))
    body = html_mod.escape(msg.get("body", "(no body)"))

    return HTMLResponse(
        _EMAIL_HTML_TMPL.format(
            subject=subject, from_addr=from_addr,
            to_addr=to_addr, date=date, body=body,
        )
    )


@router.get("/messages/{uuid}/conversation")
def get_conversation(uuid: str, limit: int = 20, email_svc: EmailService = Depends(get_email_service)):
    """Get all messages in the same conversation thread as the given message."""
    msgs = email_svc.get_conversation(uuid, limit=limit)
    return {"messages": [dict(m) for m in msgs], "total": len(msgs)}


# (send, trash, batch, export/import eml, attachments moved to email_actions.py)
