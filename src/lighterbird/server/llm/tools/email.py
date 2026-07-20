"""LLM tools for the email domain.

Tools:
    - ``email.find`` — Search messages by content/sender/date/folder
    - ``email.read`` — Full message body and metadata by UUID
    - ``email.send`` — Compose and send a new email
    - ``email.reply`` — Reply to an existing thread
    - ``email.forward`` — Forward a message
    - ``email.draft`` — Save a draft without sending
    - ``email.trash`` — Move a message to trash
    - ``email.archive`` — Archive a message by UUID
    - ``email.accounts.find`` — List email accounts
    - ``email.accounts.read`` — Get account details by email
    - ``email.accounts.create`` — Add a new email account
    - ``email.accounts.update`` — Modify account settings
    - ``email.accounts.delete`` — Remove an email account
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lightercore.permissions import PermissionLevel

from lighterbird.server.deps import get_email_service
from lighterbird.server.llm.tools import llm_tool


# ── Helper ────────────────────────────────────────────────────────────────────


def _parse_iso_date(value: str | None) -> str | None:
    """Convert an ISO date string to the format expected by the service.

    Accepts ``"2026-01-01"`` or full ISO 8601 and returns
    ``"2026-01-01T00:00:00"`` style for DB comparison.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return value


def _preview(data: dict[str, Any], max_body: int = 500) -> dict[str, Any]:
    """Return a preview dict with truncated body."""
    result = dict(data)
    body = result.get("body", "") or ""
    if len(body) > max_body:
        result["body_preview"] = body[:max_body] + "..."
    else:
        result["body_preview"] = body
    result.pop("body", None)
    # Remove large binary fields
    result.pop("headers", None)
    result.pop("raw_headers", None)
    return result


# ── Find messages ─────────────────────────────────────────────────────────────


@llm_tool(
    name="email.find",
    description=(
        "Search emails by content, sender, recipient, date range, folder, "
        "or attachment presence. Returns matching messages with previews "
        "(first 500 chars of body). Use email.read to get the full body."
    ),
    params=[
        {"name": "query", "type": "string", "description": "Free-text search across subject and body"},
        {"name": "sender", "type": "string", "description": "Sender email or display name pattern"},
        {"name": "recipient", "type": "string", "description": "Recipient email or display name pattern"},
        {"name": "account", "type": "string", "description": "Account email to scope search"},
        {"name": "folder", "type": "string", "description": "Specific folder path (e.g. 'INBOX')"},
        {"name": "after_date", "type": "string", "description": "ISO date filter (e.g. '2026-01-01')"},
        {"name": "before_date", "type": "string", "description": "ISO date filter (e.g. '2026-07-17')"},
        {"name": "has_attachments", "type": "boolean", "description": "Filter by attachment presence"},
        {"name": "max_results", "type": "number", "description": "Maximum results (default 20)"},
        {"name": "offset", "type": "number", "description": "Result offset for pagination (default 0)"},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_email_find(**kwargs: Any) -> dict:
    """Search emails with filters, returning previews."""
    service = get_email_service()
    limit = int(kwargs.get("max_results", 20))
    offset = int(kwargs.get("offset", 0))

    filters: dict[str, Any] = {}
    if kwargs.get("query"):
        filters["query"] = kwargs["query"]
    if kwargs.get("sender"):
        filters["from"] = kwargs["sender"]
    if kwargs.get("recipient"):
        filters["to"] = kwargs["recipient"]
    if kwargs.get("account"):
        filters["account"] = kwargs["account"]
    if kwargs.get("folder"):
        filters["folder"] = [kwargs["folder"]]
    if kwargs.get("after_date"):
        after = _parse_iso_date(kwargs["after_date"])
        if after:
            filters["after"] = after
    if kwargs.get("before_date"):
        before = _parse_iso_date(kwargs["before_date"])
        if before:
            filters["before"] = before

    try:
        rows = service.search_messages(filters, limit=limit + offset)
        if offset > 0:
            rows = rows[offset:]
        results = [_preview(r) for r in rows]
        return {"success": True, "data": results, "total": len(results)}
    except Exception as exc:
        return {"success": False, "error": f"Email search failed: {exc}"}


# ── Read a message ────────────────────────────────────────────────────────────


@llm_tool(
    name="email.read",
    description="Get the full message body and all metadata for an email by UUID.",
    params=[
        {"name": "uuid", "type": "string", "description": "Message UUID", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_email_read(uuid: str = "") -> dict:
    """Get full message details by UUID."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_email_service()
    try:
        msg = service.get(uuid)
        if not msg:
            return {"success": False, "error": f"Message not found: {uuid}"}
        return {"success": True, "data": dict(msg)}
    except Exception as exc:
        return {"success": False, "error": f"Failed to read message: {exc}"}


# ── Send an email ─────────────────────────────────────────────────────────────


@llm_tool(
    name="email.send",
    description="Compose and send a new email. Returns the sent message info.",
    params=[
        {"name": "account", "type": "string", "description": "Sender account email", "required": True},
        {"name": "to", "type": "string", "description": "Comma-separated recipient email addresses", "required": True},
        {"name": "subject", "type": "string", "description": "Email subject line", "required": True},
        {"name": "body", "type": "string", "description": "Email body text (plain text or markdown)"},
        {"name": "cc", "type": "string", "description": "Comma-separated CC recipients"},
        {"name": "bcc", "type": "string", "description": "Comma-separated BCC recipients"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_email_send(**kwargs: Any) -> dict:
    """Compose and send a new email."""
    account = kwargs.get("account", "")
    to_str = kwargs.get("to", "")
    subject = kwargs.get("subject", "")
    body = kwargs.get("body", "")
    cc_str = kwargs.get("cc", "")
    bcc_str = kwargs.get("bcc", "")

    if not account:
        return {"success": False, "error": "account is required"}
    if not to_str:
        return {"success": False, "error": "recipient (to) is required"}
    if not subject:
        return {"success": False, "error": "subject is required"}

    to_list = [addr.strip() for addr in to_str.split(",") if addr.strip()]
    cc_list = [addr.strip() for addr in cc_str.split(",") if addr.strip()] if cc_str else None
    bcc_list = [addr.strip() for addr in bcc_str.split(",") if addr.strip()] if bcc_str else None

    service = get_email_service()
    try:
        result = service.send_email(
            account_email=account,
            to=to_list,
            subject=subject,
            body=body,
            cc=cc_list,
            bcc=bcc_list,
        )
        return {"success": True, "data": result}
    except Exception as exc:
        return {"success": False, "error": f"Failed to send email: {exc}"}


# ── Reply ─────────────────────────────────────────────────────────────────────


@llm_tool(
    name="email.reply",
    description="Reply to an existing email thread. Composes the reply body as the LLM sees fit.",
    params=[
        {"name": "uuid", "type": "string", "description": "UUID of the message to reply to", "required": True},
        {"name": "body", "type": "string", "description": "Reply body text", "required": True},
        {"name": "reply_all", "type": "boolean", "description": "Reply to all recipients (default false)"},
        {"name": "account", "type": "string", "description": "Account email (auto-resolved if omitted)"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_email_reply(**kwargs: Any) -> dict:
    """Reply to an existing message thread."""
    uuid = kwargs.get("uuid", "")
    body = kwargs.get("body", "")
    reply_all = kwargs.get("reply_all", False)
    account = kwargs.get("account", "")

    if not uuid:
        return {"success": False, "error": "uuid is required"}
    if not body:
        return {"success": False, "error": "body is required"}

    service = get_email_service()
    try:
        original = service.get(uuid)
        if not original:
            return {"success": False, "error": f"Original message not found: {uuid}"}

        to_addr = original.get("from_addr", "")
        subject = original.get("subject", "")
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        cc_list = None
        if reply_all:
            cc_raw = original.get("to_recipients", "")
            cc_list = [a.strip() for a in cc_raw.split(",") if a.strip()]

        acct = account or original.get("account_email", "")
        if not acct:
            return {"success": False, "error": "Could not determine sender account"}

        result = service.send_email(
            account_email=acct,
            to=[to_addr],
            subject=subject,
            body=body,
            cc=cc_list,
            in_reply_to=uuid,
        )
        return {"success": True, "data": result}
    except Exception as exc:
        return {"success": False, "error": f"Failed to reply: {exc}"}


# ── Forward ───────────────────────────────────────────────────────────────────


@llm_tool(
    name="email.forward",
    description="Forward an existing message to new recipients.",
    params=[
        {"name": "uuid", "type": "string", "description": "UUID of the message to forward", "required": True},
        {"name": "to", "type": "string", "description": "Comma-separated recipient email addresses", "required": True},
        {"name": "body", "type": "string", "description": "Optional additional body text"},
        {"name": "account", "type": "string", "description": "Account email (auto-resolved if omitted)"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_email_forward(**kwargs: Any) -> dict:
    """Forward a message to new recipients."""
    uuid = kwargs.get("uuid", "")
    to_str = kwargs.get("to", "")
    body = kwargs.get("body", "")
    account = kwargs.get("account", "")

    if not uuid:
        return {"success": False, "error": "uuid is required"}
    if not to_str:
        return {"success": False, "error": "recipient (to) is required"}

    to_list = [a.strip() for a in to_str.split(",") if a.strip()]
    service = get_email_service()

    try:
        original = service.get(uuid)
        if not original:
            return {"success": False, "error": f"Original message not found: {uuid}"}

        subject = original.get("subject", "")
        if not subject.lower().startswith("fw"):
            subject = f"Fwd: {subject}"

        acct = account or original.get("account_email", "")
        if not acct:
            return {"success": False, "error": "Could not determine sender account"}

        forwarded_body = body if body else f"(Forwarded message)"
        result = service.send_email(
            account_email=acct,
            to=to_list,
            subject=subject,
            body=forwarded_body,
        )
        return {"success": True, "data": result}
    except Exception as exc:
        return {"success": False, "error": f"Failed to forward: {exc}"}


# ── Draft ─────────────────────────────────────────────────────────────────────


@llm_tool(
    name="email.draft",
    description="Save an email as a draft without sending. Returns the draft UUID.",
    params=[
        {"name": "account", "type": "string", "description": "Sender account email", "required": True},
        {"name": "to", "type": "string", "description": "Comma-separated recipient email addresses"},
        {"name": "subject", "type": "string", "description": "Email subject line"},
        {"name": "body", "type": "string", "description": "Email body text"},
        {"name": "cc", "type": "string", "description": "Comma-separated CC recipients"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_email_draft(**kwargs: Any) -> dict:
    """Save an email draft without sending."""
    account = kwargs.get("account", "")
    to_str = kwargs.get("to", "")
    subject = kwargs.get("subject", "") or "(no subject)"
    body = kwargs.get("body", "")
    cc_str = kwargs.get("cc", "")

    if not account:
        return {"success": False, "error": "account is required"}

    from lighterbird.core.storage import save_draft

    draft_data = {
        "account": account,
        "to": to_str,
        "cc": cc_str,
        "subject": subject,
        "body": body,
    }

    try:
        draft = save_draft(domain="email", title=subject, data=draft_data)
        return {"success": True, "data": {"uuid": draft.get("uuid", ""), "title": subject}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to save draft: {exc}"}


# ── Trash ─────────────────────────────────────────────────────────────────────


@llm_tool(
    name="email.trash",
    description="Move one or more messages to the trash folder (reversible).",
    params=[
        {"name": "uuid", "type": "string", "description": "Message UUID to trash", "required": True},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_email_trash(uuid: str = "") -> dict:
    """Move a message to trash."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_email_service()
    try:
        service.trash_message(uuid)
        return {"success": True, "data": {"uuid": uuid, "trashed": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to trash message: {exc}"}


# ── Archive ────────────────────────────────────────────────────────────────────


@llm_tool(
    name="email.archive",
    description="Archive a message by UUID. Moves the message out of the inbox.",
    params=[
        {"name": "uuid", "type": "string", "description": "Message UUID to archive", "required": True},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_email_archive(uuid: str = "") -> dict:
    """Archive a message."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_email_service()
    try:
        service.move_message(uuid, "Archive")
        return {"success": True, "data": {"uuid": uuid, "archived": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to archive message: {exc}"}


# ═══════════════════════════════════════════════════════════════════════════════
# Email Account management
# ═══════════════════════════════════════════════════════════════════════════════


@llm_tool(
    name="email.accounts.find",
    description="List all configured email accounts with their basic info (no passwords).",
    params=[
        {"name": "max_results", "type": "number", "description": "Maximum results (default 50)"},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_email_accounts_find(**kwargs: Any) -> dict:
    """List all email accounts (without passwords)."""
    service = get_email_service()
    try:
        accounts = service.list_accounts()
        limit = int(kwargs.get("max_results", 50))
        safe = []
        for a in (accounts or [])[:limit]:
            safe.append({
                k: v for k, v in a.items()
                if k not in ("password",)
            })
        return {"success": True, "data": safe, "total": len(safe)}
    except Exception as exc:
        return {"success": False, "error": f"Failed to list accounts: {exc}"}


@llm_tool(
    name="email.accounts.read",
    description="Get details for a specific email account by its email address.",
    params=[
        {"name": "email", "type": "string", "description": "Account email address", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_email_accounts_read(email: str = "") -> dict:
    """Get account details (without password)."""
    if not email:
        return {"success": False, "error": "email is required"}
    service = get_email_service()
    try:
        acct = service.accounts.get(email)
        if not acct:
            return {"success": False, "error": f"Account not found: {email}"}
        safe = {k: v for k, v in dict(acct).items() if k not in ("password",)}
        return {"success": True, "data": safe}
    except Exception as exc:
        return {"success": False, "error": f"Failed to get account: {exc}"}


@llm_tool(
    name="email.accounts.create",
    description="Add a new email account with IMAP and SMTP settings.",
    params=[
        {"name": "email", "type": "string", "description": "Account email address", "required": True},
        {"name": "password", "type": "string", "description": "Account password or app password", "required": True},
        {"name": "imap_server", "type": "string", "description": "IMAP server hostname"},
        {"name": "imap_port", "type": "number", "description": "IMAP server port (default 993)"},
        {"name": "smtp_server", "type": "string", "description": "SMTP server hostname"},
        {"name": "smtp_port", "type": "number", "description": "SMTP server port (default 587)"},
        {"name": "display_name", "type": "string", "description": "Display name for sent emails"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_email_accounts_create(**kwargs: Any) -> dict:
    """Add a new email account."""
    email = kwargs.get("email", "")
    password = kwargs.get("password", "")

    if not email:
        return {"success": False, "error": "email is required"}
    if not password:
        return {"success": False, "error": "password is required"}

    data = {
        "email": email,
        "imap_server": kwargs.get("imap_server", ""),
        "imap_port": int(kwargs.get("imap_port", 993)),
        "smtp_server": kwargs.get("smtp_server", ""),
        "smtp_port": int(kwargs.get("smtp_port", 587)),
        "display_name": kwargs.get("display_name", ""),
        "imap_use_ssl": 1,
    }

    service = get_email_service()
    try:
        result = service.create_account(data, password)
        return {"success": True, "data": {"email": email}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to create account: {exc}"}


@llm_tool(
    name="email.accounts.update",
    description="Modify an existing email account's settings. Only provided fields are updated.",
    params=[
        {"name": "email", "type": "string", "description": "Account email address to modify", "required": True},
        {"name": "password", "type": "string", "description": "New account password"},
        {"name": "imap_server", "type": "string", "description": "IMAP server hostname"},
        {"name": "imap_port", "type": "number", "description": "IMAP server port"},
        {"name": "smtp_server", "type": "string", "description": "SMTP server hostname"},
        {"name": "smtp_port", "type": "number", "description": "SMTP server port"},
        {"name": "display_name", "type": "string", "description": "Display name for sent emails"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_email_accounts_update(**kwargs: Any) -> dict:
    """Modify an email account."""
    email = kwargs.get("email", "")
    if not email:
        return {"success": False, "error": "email is required"}

    data: dict[str, Any] = {}
    if kwargs.get("imap_server"):
        data["imap_server"] = kwargs["imap_server"]
    if kwargs.get("imap_port"):
        data["imap_port"] = int(kwargs["imap_port"])
    if kwargs.get("smtp_server"):
        data["smtp_server"] = kwargs["smtp_server"]
    if kwargs.get("smtp_port"):
        data["smtp_port"] = int(kwargs["smtp_port"])
    if kwargs.get("display_name"):
        data["display_name"] = kwargs["display_name"]

    service = get_email_service()
    try:
        result = service.accounts.update(email, data)
        if kwargs.get("password"):
            service.accounts.set_password(email, kwargs["password"])
        return {"success": True, "data": {"email": email, "updated": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to update account: {exc}"}


@llm_tool(
    name="email.accounts.delete",
    description="Permanently remove an email account and all its messages. This is destructive.",
    params=[
        {"name": "email", "type": "string", "description": "Account email address to delete", "required": True},
    ],
    permission_level=PermissionLevel.DESTRUCTIVE,
)
def llm_email_accounts_delete(email: str = "") -> dict:
    """Delete an email account permanently."""
    if not email:
        return {"success": False, "error": "email is required"}
    service = get_email_service()
    try:
        service.delete_account(email)
        return {"success": True, "data": {"email": email, "deleted": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to delete account: {exc}"}
