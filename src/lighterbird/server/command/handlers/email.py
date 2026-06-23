"""Command handlers for the ``!email`` domain.

Registered paths:
    - email.list
    - email.read
    - email.send
    - email.search
    - email.sync
    - email.trash
    - email.archive
    - email.account.add
    - email.account.list
    - email.account.modify
    - email.account.remove
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.command.response import normalize_account, normalize_message
from lighterbird.server.deps import get_email_service
from lighterbird.email.service import EmailService


# ── Handlers ────────────────────────────────────────────────────────────


@command("email.list")
def email_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email list [--limit N]"""
    svc: EmailService = get_email_service()
    limit = int(flags.get("limit", 20))
    messages = [normalize_message(m) for m in svc.list_messages(limit=limit)]
    return {
        "type": "status",
        "title": "Inbox",
        "data": {"messages": messages, "total": len(messages)},
    }


@command("email.read")
def email_read(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email read <uuid>"""
    if not remaining:
        raise CommandValidationError("Missing message UUID.", "Usage: !email read <uuid>")
    uuid = remaining[0]
    svc: EmailService = get_email_service()
    msg = svc.get_message(uuid)
    if not msg:
        raise CommandValidationError(f"Message not found: {uuid[:8]}")
    return {"type": "email", "title": msg.get("subjekto", "(no subject)"), "data": normalize_message(msg)}


@command("email.send")
def email_send(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email send <to> <subject> [body] [--account uuid] [--cc email]"""
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing required args: <to> <subject> [body]",
            "Usage: !email send recipient@example.com \"Subject\" \"Body\" --account <uuid>",
        )
    to_str = remaining[0]
    subject = remaining[1]
    body = " ".join(remaining[2:]) if len(remaining) > 2 else ""
    account_uuid = flags.get("account", "")
    cc_str = flags.get("cc", "")

    svc: EmailService = get_email_service()

    # If no account specified, pick the first one
    if not account_uuid:
        accounts = svc.list_accounts()
        if not accounts:
            raise CommandValidationError("No email accounts configured.", "Add one with: !email account add")
        account_uuid = accounts[0]["uuid"]

    svc.send_email(account_uuid, [to_str], subject, body, cc=[cc_str] if cc_str else None)
    return {"type": "status", "title": "Sent", "data": {"to": to_str, "subject": subject}}


@command("email.search")
def email_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email search [--from] [--subject] [--body] [--after] [--before] [--limit]"""
    svc: EmailService = get_email_service()
    filters = {}
    if flags.get("from"):
        filters["from"] = flags["from"]
    if flags.get("subject"):
        filters["subject"] = flags["subject"]
    if flags.get("body"):
        filters["body"] = flags["body"]
    if flags.get("after"):
        filters["after"] = flags["after"]
    if flags.get("before"):
        filters["before"] = flags["before"]
    limit = int(flags.get("limit", 50))
    # Any remaining tokens treated as a free-text query
    if remaining:
        filters["query"] = " ".join(remaining)

    if filters:
        messages = [normalize_message(m) for m in svc.search_messages(filters, limit=limit)]
    else:
        messages = [normalize_message(m) for m in svc.list_messages(limit=limit)]
    return {
        "type": "status",
        "title": "Search Results",
        "data": {"messages": messages, "total": len(messages)},
    }


@command("email.sync")
def email_sync(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sync [uuid] [--all]

    Without arguments, syncs the first listed account.
    Use ``--all`` to sync all accounts.
    Provide a UUID to sync a specific account.
    """
    svc: EmailService = get_email_service()
    do_all = "all" in flags

    if remaining and not do_all:
        result = svc.sync_account(remaining[0])
        data = result.to_dict()
        title = "Sync Complete (with errors)" if data.get("errors") else "Synced"
        return {"type": "status", "title": title, "data": data}

    # Sync all accounts
    results = svc.sync_all()
    total_new = sum(r.get("new", 0) for r in results.values())
    total_errors = sum(len(r.get("errors", [])) for r in results.values())
    error_details = {}
    for acct_uuid, r in results.items():
        if r.get("errors"):
            # Resolve account email for helpful display
            acct = svc.get_account(acct_uuid)
            label = acct.get("retposto", acct_uuid[:8]) if acct else acct_uuid[:8]
            error_details[label] = r["errors"]

    title = "Sync Complete (with errors)" if total_errors > 0 else "Sync Complete"
    summary = f"{total_new} new items synced."
    if total_errors > 0:
        err_lines = [f"  {label}: {'; '.join(errs[:3])}" for label, errs in error_details.items()]
        summary += f"\n{total_errors} error(s):\n" + "\n".join(err_lines[:5])
        if total_errors > 5:
            summary += f"\n  ... and {total_errors - 5} more"
    return {
        "type": "status",
        "title": title,
        "data": {
            "new": total_new,
            "account_count": len(results),
            "errors": total_errors,
            "error_details": error_details or None,
            "_summary": summary,
        },
    }


@command("email.trash")
def email_trash(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email trash <uuid>"""
    if not remaining:
        raise CommandValidationError("Missing message UUID.", "Usage: !email trash <uuid>")
    svc: EmailService = get_email_service()
    svc.trash_message(remaining[0])
    return {"type": "status", "title": "Trashed", "data": {"uuid": remaining[0][:8]}}


@command("email.archive")
def email_archive(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email archive <uuid>"""
    # Archive maps to trash for now (no dedicated archive folder support yet)
    if not remaining:
        raise CommandValidationError("Missing message UUID.", "Usage: !email archive <uuid>")
    svc: EmailService = get_email_service()
    svc.trash_message(remaining[0])
    return {"type": "status", "title": "Archived", "data": {"uuid": remaining[0][:8]}}


# ── Account sub-commands ────────────────────────────────────────────────


@command("email.account.list")
def account_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email account list"""
    svc: EmailService = get_email_service()
    accounts = [normalize_account(a) for a in svc.list_accounts()]
    return {"type": "status", "title": "Email Accounts", "data": {"accounts": accounts}}


@command("email.account.add")
def account_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email account add <email> [--imap HOST] [--smtp HOST] [--password PW] [--name NAME]"""
    if not remaining:
        raise CommandValidationError(
            "Missing email address.",
            "Usage: !email account add user@example.com [--imap imap.example.com] [--smtp smtp.example.com] [--password ...] [--name NAME]",
        )
    email_addr = remaining[0]
    imap_server = flags.get("imap", "")
    smtp_server = flags.get("smtp", "")
    password = flags.get("password", "")
    name = flags.get("name", "")

    from lighterbird.server.schemas import AccountCreate
    from lighterbird.email.server_detect import detect_servers

    detected = detect_servers(email_addr, imap_server=imap_server, smtp_server=smtp_server)
    acct_data = {
        "nomo": name or email_addr.split("@")[0],
        "retposto": email_addr,
        "imap_servilo": detected["imap"],
        "imap_haveno": 993,
        "imap_ssl": 1,
        "smtp_servilo": detected["smtp"],
        "smtp_haveno": 587,
        "smtp_tls": 1,
        "imap_uzantonomo": email_addr,
        "smtp_uzantonomo": email_addr,
    }
    svc: EmailService = get_email_service()
    acct = svc.create_account(acct_data, password)
    return {
        "type": "status",
        "title": "Account Added",
        "data": {"uuid": acct["uuid"], "email": email_addr},
    }


@command("email.account.modify")
def account_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email account modify <uuid> [--name NAME] [--password PW] [--imap-server HOST] [--smtp-server HOST]"""
    if not remaining:
        raise CommandValidationError("Missing account UUID.", "Usage: !email account modify <uuid> [--name ...] [--password ...]")
    uuid = remaining[0]
    svc: EmailService = get_email_service()
    acct = svc.get_account(uuid)
    if not acct:
        raise CommandValidationError(f"Account not found: {uuid[:8]}")

    updates = {}
    if "name" in flags:
        updates["nomo"] = flags["name"]
    if "imap_server" in flags:
        updates["imap_servilo"] = flags["imap_server"]
    if "smtp_server" in flags:
        updates["smtp_servilo"] = flags["smtp_server"]
    if updates:
        # Use CRUD update directly
        svc.accounts.update(uuid, updates)
    if "password" in flags:
        svc.accounts.set_password(uuid, flags["password"])
    return {"type": "status", "title": "Account Modified", "data": {"uuid": uuid[:8]}}


@command("email.account.remove")
def account_remove(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email account remove <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError("Missing account UUID(s).", "Usage: !email account remove <uuid> [uuid...]")
    svc: EmailService = get_email_service()
    succeeded = []
    for uuid in remaining:
        try:
            svc.delete_account(uuid)
            succeeded.append(uuid[:8])
        except Exception:
            pass
    return {
        "type": "status",
        "title": "Account(s) Removed",
        "data": {"removed": succeeded},
    }
