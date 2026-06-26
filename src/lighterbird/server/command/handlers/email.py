"""Command handlers for the ``!email`` domain.

Registered paths:
    - email.list
    - email.read
    - email.send
    - email.search
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


@command("email")
def email_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email — Show available email subcommands."""
    return {
        "type": "status",
        "title": "Email Commands",
        "data": {
            "_summary": (
                "Available !email commands:\n"
                "  !email list              — List inbox messages\n"
                "  !email read <uuid>       — Read a message\n"
                "  !email send              — Send an email\n"
                "  !email search            — Search messages\n"
                "  !email trash <uuid>      — Trash a message\n"
                "  !email archive <uuid>    — Archive a message\n"
                "  !email account list      — List email accounts\n"
                "  !email account add       — Add an email account\n"
                "  !email account modify    — Modify an email account\n"
                "  !email account remove    — Remove an email account\n"
                "  !email sieve list        — List Sieve scripts\n"
                "  !email sieve add         — Add a Sieve script\n"
                "  !email sieve modify      — Modify a Sieve script\n"
                "  !email sieve delete      — Delete a Sieve script\n"
                "  !email sieve activate    — Activate on an account\n"
                "  !email sieve deactivate  — Deactivate on an account"
            ),
        },
    }


@command("email.list")
def email_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email list [--limit N] [--folder NAME] [--not-folder NAME] [--all]

    By default excludes Trash, Spam, and Junk folders.
    Use ``--all`` to include all folders (including trash).
    Use ``--folder`` to filter to specific folder(s); comma-separated.
    Use ``--not-folder`` to exclude specific folder(s); comma-separated.
    Folder names use the ``{email}/{folder}`` convention, e.g.
    ``user@gmail.com/INBOX``.
    """
    svc: EmailService = get_email_service()
    limit = int(flags.get("limit", 20))
    include_all = "all" in flags
    folder_filter = flags.get("folder", "")
    not_folder_filter = flags.get("not-folder", "")

    filters = {}
    if folder_filter:
        # --folder can specify comma-separated: INBOX,Sent or email/folder format
        folder_names = [f.strip() for f in folder_filter.split(",") if f.strip()]
        resolved_folders: list[str] = []
        resolved_account: str | None = None

        for folder_name in folder_names:
            parts = folder_name.split("/", 1)
            if len(parts) == 2:
                acct_email, fname = parts
                accounts = svc.list_accounts()
                for acct in accounts:
                    if acct.get("retposto", "").lower() == acct_email.lower():
                        if resolved_account is None:
                            resolved_account = acct["uuid"]
                        resolved_folders.append(fname)
                        break
                else:
                    # Account not found; use folder name as-is
                    resolved_folders.append(folder_name)
            else:
                resolved_folders.append(folder_name)

        if resolved_account:
            filters["account"] = resolved_account
        if resolved_folders:
            filters["folder"] = resolved_folders

    if not_folder_filter:
        exclude_names = [f.strip() for f in not_folder_filter.split(",") if f.strip()]
        filters["exclude_folder"] = exclude_names

    if not folder_filter and not include_all:
        # Default: exclude trash-like folders
        existing_exclude = filters.get("exclude_folder", [])
        filters["exclude_folder"] = existing_exclude + ["Trash", "Spam", "Junk", "Bin"]

    messages = [normalize_message(m) for m in svc.search_messages(filters, limit=limit)]
    title_suffix = f" ({folder_filter})" if folder_filter else ""
    if not_folder_filter:
        title_suffix += f" (excl. {not_folder_filter})"
    if not folder_filter and not include_all:
        title_suffix = "" if title_suffix else " (no trash)"

    # Build frontend-compatible filter params for in-tab search bar
    frontend_filters = {}
    if "account" in filters:
        frontend_filters["account_uuid"] = filters["account"]
    if "folder" in filters:
        fld = filters["folder"]
        frontend_filters["folder"] = fld[0] if isinstance(fld, list) else fld

    return {
        "type": "email-list",
        "title": f"Inbox{title_suffix}",
        "data": {"messages": messages, "total": len(messages), "filters": frontend_filters},
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

    # Build frontend-compatible filter params for in-tab search bar
    frontend_filters = {}
    if flags.get("from"):
        frontend_filters["from"] = flags["from"]
    if flags.get("subject"):
        frontend_filters["subject"] = flags["subject"]
    if flags.get("after"):
        frontend_filters["after"] = flags["after"]
    if flags.get("before"):
        frontend_filters["before"] = flags["before"]

    query = " ".join(remaining) if remaining else ""

    return {
        "type": "email-list",
        "title": "Search Results",
        "data": {
            "messages": messages,
            "total": len(messages),
            "filters": frontend_filters,
            "query": query,
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
    """!email account add <email> [--imap HOST] [--smtp HOST] [--password PW] [--name NAME]

    IMAP/SMTP servers are auto-detected for common providers.
    Only specify --imap or --smtp to override auto-detection.
    """
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
    if "managesieve_host" in flags:
        updates["managesieve_host"] = flags["managesieve_host"]
    if "managesieve_port" in flags:
        updates["managesieve_port"] = int(flags["managesieve_port"])
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
