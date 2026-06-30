"""Command handlers for the ``!email`` domain.

Registered paths:
    - email.list
    - email.read
    - email.send
    - email.reply
    - email.forward
    - email.search
    - email.trash
    - email.archive
    - email.account.add
    - email.account.list
    - email.account.modify
    - email.account.remove
    - email.signature.add
    - email.signature.list
    - email.signature.modify
    - email.signature.delete
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.command.response import normalize_message
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
                "  !email reply <uuid>      — Reply to a message\n"
                "  !email reply-all <uuid>  — Reply-all to a message\n"
                "  !email forward <uuid>    — Forward a message\n"
                "  !email search            — Search messages\n"
                "  !email trash <uuid>      — Trash a message\n"
                "  !email archive <uuid>    — Archive a message\n"
                "  !email account list      — List email accounts\n"
                "  !email account add       — Add an email account\n"
                "  !email account modify    — Modify an email account\n"
                "  !email account remove    — Remove an email account\n"
                "  !email signature list    — List account signatures\n"
                "  !email signature add     — Set a signature for an account\n"
                "  !email signature modify  — Modify an account signature\n"
                "  !email signature delete  — Delete an account signature\n"
                "  !email sieve list        — List Sieve scripts\n"
                "  !email sieve add         — Add a Sieve script\n"
                "  !email sieve modify      — Modify a Sieve script\n"
                "  !email sieve delete      — Delete a Sieve script\n"
                "  !email sieve activate    — Activate on an account\n"
                "  !email sieve deactivate  — Deactivate on an account\n"
                "  !email draft             — List / recall email drafts"
            ),
        },
    }


@command("email.list")
def email_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email list [--limit N] [--folder NAME] [--not-folder NAME] [--all]
                  [--sort newest|oldest|sender] [--group conversation]

    By default excludes Trash, Spam, and Junk folders.
    Use ``--all`` to include all folders (including trash).
    Use ``--folder`` to filter to specific folder(s); comma-separated.
    Use ``--not-folder`` to exclude specific folder(s); comma-separated.
    Folder names use the ``{email}/{folder}`` convention, e.g.
    ``user@gmail.com/INBOX``.
    ``--sort`` controls display order: newest (default), oldest, sender.
    ``--group`` groups by conversation thread.
    """
    svc: EmailService = get_email_service()
    limit = int(flags.get("limit", 20))
    include_all = "all" in flags
    folder_filter = flags.get("folder", "")
    not_folder_filter = flags.get("not-folder", "")
    sort_by = flags.get("sort", "newest")
    group_by = flags.get("group", "")

    filters = {}
    if folder_filter:
        folder_names = [f.strip() for f in folder_filter.split(",") if f.strip()]
        resolved_account: str | None = None

        for folder_name in folder_names:
            parts = folder_name.split("/", 1)
            if len(parts) == 2:
                acct_email, fname = parts
                accounts = svc.list_accounts()
                for acct in accounts:
                    if acct.get("email", "").lower() == acct_email.lower():
                        if resolved_account is None:
                            resolved_account = acct["email"]
                        filters["folder"] = [fname]
                        break
                else:
                    filters.setdefault("folder", []).append(folder_name)
            else:
                filters.setdefault("folder", []).append(folder_name)

        if resolved_account:
            filters["account"] = resolved_account

    if not_folder_filter:
        exclude_names = [f.strip() for f in not_folder_filter.split(",") if f.strip()]
        filters["exclude_folder"] = exclude_names

    if not folder_filter and not include_all:
        existing_exclude = filters.get("exclude_folder", [])
        filters["exclude_folder"] = existing_exclude + ["Trash", "Spam", "Junk", "Bin"]

    messages = [normalize_message(m) for m in svc.search_messages(filters, limit=limit)]
    title_suffix = f" ({folder_filter})" if folder_filter else ""
    if not_folder_filter:
        title_suffix += f" (excl. {not_folder_filter})"
    if not folder_filter and not include_all:
        title_suffix = "" if title_suffix else " (no trash)"

    frontend_filters = {}
    if "account" in filters:
        frontend_filters["account_email"] = filters["account"]
    if "folder" in filters:
        fld = filters["folder"]
        frontend_filters["folder"] = fld[0] if isinstance(fld, list) else fld
    if sort_by:
        frontend_filters["sort"] = sort_by
    if group_by:
        frontend_filters["group"] = group_by

    return {
        "type": "email-list",
        "title": f"Inbox{title_suffix}",
        "data": {
            "messages": messages,
            "total": len(messages),
            "filters": frontend_filters,
        },
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
    return {"type": "email", "title": msg.get("subject", "(no subject)"), "data": normalize_message(msg)}


@command("email.send")
def email_send(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email send <to> <subject> [body] [--account <email>] [--cc email]
                    [--bcc email] [--priority N] [--body-format fmt]
                    [--file <name:base64>]

    Sends an email.  ``<to>`` and ``<subject>`` are required; ``<body>``
    is optional.  Use ``--cc`` / ``--bcc`` for additional recipients,
    ``--priority`` (1-5) to set importance, ``--body-format`` to choose
    markdown (default), html, or plain, and ``--file`` for attachments
    (repeatable, format: ``<filename>:<base64>``).
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing required args: <to> <subject> [body]",
            "Usage: !email send recipient@example.com \"Subject\" \"Body\" --account <email>",
        )
    to_str = remaining[0]
    subject = remaining[1]
    body = " ".join(remaining[2:]) if len(remaining) > 2 else ""
    account_email = flags.get("account", "")
    cc_str = flags.get("cc", "")
    bcc_str = flags.get("bcc", "")
    priority_str = flags.get("priority", "3")
    body_format = flags.get("body-format", "markdown")
    file_flags = flags.get("file", "")

    svc: EmailService = get_email_service()

    # If no account specified, pick the first one
    if not account_email:
        accounts = svc.list_accounts()
        if not accounts:
            raise CommandValidationError("No email accounts configured.", "Add one with: !email account add")
        account_email = accounts[0]["email"]

    # Parse priority
    try:
        priority = int(priority_str)
        if priority < 1 or priority > 5:
            raise ValueError
    except ValueError:
        raise CommandValidationError(
            f"Invalid priority: {priority_str}. Must be 1 (highest) to 5 (lowest)."
        )

    # Validate body-format
    if body_format not in ("markdown", "html", "plain"):
        raise CommandValidationError(
            f"Invalid body-format: {body_format}. Choose markdown, html, or plain."
        )

    to_list = [t.strip() for t in to_str.split(",") if t.strip()]
    cc_list = [t.strip() for t in cc_str.split(",") if t.strip()] if cc_str else None
    bcc_list = [t.strip() for t in bcc_str.split(",") if t.strip()] if bcc_str else None

    # Parse --file flags: "name:base64,..." or multiple --file occurrences
    attachments = None
    if file_flags:
        attachments = []
        for item in file_flags.split(","):
            item = item.strip()
            if ":" in item:
                name, data = item.split(":", 1)
                attachments.append({"name": name, "data": data})
            else:
                attachments.append({"name": item, "data": ""})

    svc.send_email(account_email, to_list, subject, body,
                   cc=cc_list, bcc=bcc_list, priority=priority,
                   body_format=body_format,
                   attachments=attachments)
    return {"type": "status", "title": "Sent", "data": {"to": to_str, "subject": subject}}


@command("email.reply")
def email_reply(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email reply <uuid> [--all]

    Opens the compose form pre-populated as a reply to the given message.
    Use ``--all`` to Reply-All (include all original recipients).
    """
    if not remaining:
        raise CommandValidationError(
            "Missing message UUID.",
            "Usage: !email reply <uuid> [--all]",
        )
    uuid = remaining[0]
    svc: EmailService = get_email_service()
    msg = svc.get_message(uuid)
    if not msg:
        raise CommandValidationError(f"Message not found: {uuid[:8]}")

    reply_all = "all" in flags
    to = msg.get("from_addr", "")
    if reply_all:
        # Include original To recipients (excluding self)
        import json as json_mod
        orig_to = json_mod.loads(msg.get("to_recipients", "[]")) if isinstance(msg.get("to_recipients"), str) else (msg.get("to_recipients") or [])
        to_list = [to]
        for r in orig_to:
            if r.strip().lower() != msg.get("account_email", "").lower():
                to_list.append(r.strip())
        to = ", ".join(to_list)

    subject = msg.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    body = msg.get("body", "") or ""
    quoted = "\n".join(f"> {line}" for line in body.split("\n"))

    return {
        "type": "form-required",
        "title": "Reply",
        "data": {
            "form": "email-send",
            "initialData": {
                "to": to,
                "subject": subject,
                "body": f"\n\n{quoted}",
                "account": msg.get("account_email", ""),
            },
        },
    }


@command("email.forward")
def email_forward(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email forward <uuid>

    Opens the compose form pre-populated as a forward of the given message.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing message UUID.",
            "Usage: !email forward <uuid>",
        )
    uuid = remaining[0]
    svc: EmailService = get_email_service()
    msg = svc.get_message(uuid)
    if not msg:
        raise CommandValidationError(f"Message not found: {uuid[:8]}")

    subject = msg.get("subject", "")
    if not subject.lower().startswith("fwd:"):
        subject = f"Fwd: {subject}"

    body = msg.get("body", "") or ""
    header = f"--- Forwarded message ---\nFrom: {msg.get('from_addr', '')}\nSubject: {msg.get('subject', '')}\nDate: {msg.get('received_at', '')}\n\n"
    forwarded = f"{header}{body}"

    return {
        "type": "form-required",
        "title": "Forward",
        "data": {
            "form": "email-send",
            "initialData": {
                "subject": subject,
                "body": f"\n\n{forwarded}",
                "account": msg.get("account_email", ""),
            },
        },
    }


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
    if remaining:
        filters["query"] = " ".join(remaining)

    if filters:
        messages = [normalize_message(m) for m in svc.search_messages(filters, limit=limit)]
    else:
        messages = [normalize_message(m) for m in svc.list_messages(limit=limit)]

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
    if not remaining:
        raise CommandValidationError("Missing message UUID.", "Usage: !email archive <uuid>")
    svc: EmailService = get_email_service()
    svc.trash_message(remaining[0])
    return {"type": "status", "title": "Archived", "data": {"uuid": remaining[0][:8]}}


# (Account sub-commands moved to email_account.py)
